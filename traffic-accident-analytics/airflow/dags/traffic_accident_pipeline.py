"""
airflow/dags/traffic_accident_pipeline.py
------------------------------------------
Apache Airflow DAG for the Traffic Accident Severity Analytics pipeline.

Why Airflow?
------------
Airflow orchestrates the pipeline as a series of dependent tasks. Each
task is a discrete unit of work. If one task fails, downstream tasks are
automatically skipped. Airflow tracks run history, allows manual retries,
and provides a web UI to monitor progress. This makes the pipeline
reproducible and observable — much better than a single monolithic script.

DAG structure
-------------
                    ┌─ extract_accidents ─┐
                    ├─ extract_vehicles   ─┤
start ──────────────┤                      ├── validate_raw_data
                    ├─ extract_casualties ─┤
                    └─ extract_weather   ──┘
                            │
                            ▼
                      create_staging
                            │
                    ┌───────┼───────┐
                    ▼       ▼       ▼
              clean_accidents  clean_vehicles  clean_casualties
                    │               │               │
                    └───────┬───────┘               │
                            ▼                       │
                      clean_weather ────────────────┘
                            │
                            ▼
                   join_accident_weather
                            │
                            ▼
                     load_postgresql
                            │
                            ▼
                   create_analytics_mart
                            │
                            ▼
                  run_data_quality_checks
                            │
                            ▼
                     pipeline_complete

Schedule: None (manually triggered)
  — set to None so the pipeline does not re-run automatically and
    accidentally exhaust the Open-Meteo API or produce duplicate records.

Idempotency
-----------
Every task is safe to re-run. The transformation layer uses
TRUNCATE + INSERT with ON CONFLICT DO NOTHING/UPDATE in PostgreSQL,
so repeated pipeline runs will not create duplicate records.
"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Make project root importable from within the Airflow worker
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator

# ── Default task arguments ─────────────────────────────────────────────────────
default_args = {
    "owner":            "traffic_analytics",
    "depends_on_past":  False,
    "start_date":       datetime(2024, 1, 1),
    "email_on_failure": False,
    "email_on_retry":   False,
    "retries":          2,
    "retry_delay":      timedelta(minutes=5),
}

# ── Task callables ─────────────────────────────────────────────────────────────
# Each callable is a thin wrapper that imports and calls the relevant module.
# Keeping imports inside the functions means Airflow workers only load what
# they need, and import errors in one module do not break the entire DAG.


def task_extract_accidents(**context):
    """Download (or locate) the UK STATS19 collision CSV → data/raw/accidents/."""
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: extract_accidents ===")

    from ingestion.accident_ingestion import ingest_accidents
    df = ingest_accidents(force_download=False)
    logger.info("Extracted %d accident records.", len(df))

    # Push row count to XCom so downstream tasks can log it
    context["ti"].xcom_push(key="accident_row_count", value=len(df))
    return len(df)


def task_extract_vehicles(**context):
    """Download (or locate) the UK STATS19 vehicle CSV → data/raw/vehicles/."""
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: extract_vehicles ===")

    from ingestion.vehicle_ingestion import ingest_vehicles
    df = ingest_vehicles(force_download=False)
    logger.info("Extracted %d vehicle records.", len(df))
    context["ti"].xcom_push(key="vehicle_row_count", value=len(df))
    return len(df)


def task_extract_casualties(**context):
    """Download (or locate) the UK STATS19 casualty CSV → data/raw/casualties/."""
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: extract_casualties ===")

    from ingestion.casualty_ingestion import ingest_casualties
    df = ingest_casualties(force_download=False)
    logger.info("Extracted %d casualty records.", len(df))
    context["ti"].xcom_push(key="casualty_row_count", value=len(df))
    return len(df)


def task_extract_weather(**context):
    """
    Fetch hourly weather from Open-Meteo for all accident grid cells.
    Uses cached Parquet files — does NOT re-call the API if cache exists.
    """
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: extract_weather ===")

    from ingestion.weather_ingestion import ingest_weather
    paths = ingest_weather(force_download=False)
    logger.info("Weather ingestion complete: %d grid cell cache files.", len(paths))
    context["ti"].xcom_push(key="weather_cache_files", value=len(paths))
    return len(paths)


def task_validate_raw_data(**context):
    """
    Basic sanity check on raw data: verify files exist and are non-empty.
    This is a lightweight pre-check before staging begins.
    """
    import logging
    import pandas as pd
    from config.config import (
        RAW_ACCIDENTS_DIR, RAW_VEHICLES_DIR,
        RAW_CASUALTIES_DIR, RAW_WEATHER_DIR,
        ACCIDENTS_FILENAME, VEHICLES_FILENAME, CASUALTIES_FILENAME,
    )

    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: validate_raw_data ===")

    checks = {
        "accidents":  RAW_ACCIDENTS_DIR / ACCIDENTS_FILENAME,
        "vehicles":   RAW_VEHICLES_DIR  / VEHICLES_FILENAME,
        "casualties": RAW_CASUALTIES_DIR / CASUALTIES_FILENAME,
    }

    for name, path in checks.items():
        # Also try any CSV in the dir in case user placed it manually
        if not path.exists():
            alternatives = list(path.parent.glob("*.csv"))
            if alternatives:
                path = alternatives[0]
                logger.warning("Using alternative file for %s: %s", name, path)
            else:
                raise FileNotFoundError(
                    f"Raw {name} file not found at {path}. "
                    f"Run extract_{name} task first or manually place the CSV."
                )
        size_mb = path.stat().st_size / (1024 * 1024)
        logger.info("Raw %s file: %s (%.1f MB)", name, path.name, size_mb)
        if size_mb < 0.01:
            raise ValueError(f"Raw {name} file appears to be empty (< 10 KB).")

    # Check weather cache
    weather_files = list(RAW_WEATHER_DIR.glob("weather_*.parquet"))
    if not weather_files:
        logger.warning(
            "No weather cache files found in %s. "
            "Weather columns will be NULL in the analytical mart. "
            "This is non-fatal.", RAW_WEATHER_DIR
        )
    else:
        logger.info("Weather cache: %d Parquet files found.", len(weather_files))

    logger.info("Raw data validation PASSED.")


def task_create_staging(**context):
    """
    Apply staging transformations to all raw datasets:
    - Normalise column names
    - Parse dates and times
    - Replace STATS19 -1 missing codes with NULL
    - Cast numeric columns
    Writes results to data/staging/
    """
    import logging
    import pandas as pd
    from config.config import RAW_ACCIDENTS_DIR, RAW_VEHICLES_DIR, RAW_CASUALTIES_DIR
    from config.config import ACCIDENTS_FILENAME, VEHICLES_FILENAME, CASUALTIES_FILENAME

    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: create_staging ===")

    from transformation.clean_accidents  import stage_accidents
    from transformation.clean_vehicles   import stage_vehicles
    from transformation.clean_casualties import stage_casualties

    # Load raw files
    def _load_raw(raw_dir, filename):
        path = raw_dir / filename
        if not path.exists():
            alternatives = list(raw_dir.glob("*.csv"))
            if alternatives:
                return pd.read_csv(alternatives[0], low_memory=False)
            raise FileNotFoundError(f"No CSV found in {raw_dir}")
        return pd.read_csv(path, low_memory=False)

    df_acc  = _load_raw(RAW_ACCIDENTS_DIR,  ACCIDENTS_FILENAME)
    df_veh  = _load_raw(RAW_VEHICLES_DIR,   VEHICLES_FILENAME)
    df_cas  = _load_raw(RAW_CASUALTIES_DIR, CASUALTIES_FILENAME)

    staged_acc = stage_accidents(df_acc)
    staged_veh = stage_vehicles(df_veh)
    staged_cas = stage_casualties(df_cas)

    logger.info(
        "Staging complete: accidents=%d, vehicles=%d, casualties=%d",
        len(staged_acc), len(staged_veh), len(staged_cas),
    )


def task_clean_accidents(**context):
    """
    Apply data-quality cleaning to staged accident data.
    Rejects records with: missing ID, invalid coords, bad date, bad severity.
    Writes cleaned CSV to data/cleaned/, rejected CSV to data/rejected/.
    """
    import logging
    import pandas as pd
    from config.config import STAGING_DIR

    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: clean_accidents ===")

    from transformation.clean_accidents import clean_accidents

    staged_path = STAGING_DIR / "accidents_staged.csv"
    if not staged_path.exists():
        raise FileNotFoundError(
            f"Staged accidents not found at {staged_path}. "
            "Run create_staging first."
        )

    df_staged = pd.read_csv(staged_path, low_memory=False)
    df_clean, df_rejected = clean_accidents(df_staged)

    logger.info(
        "Accident cleaning complete: %d clean rows, %d rejected rows.",
        len(df_clean), len(df_rejected),
    )
    context["ti"].xcom_push(key="accidents_clean_count",    value=len(df_clean))
    context["ti"].xcom_push(key="accidents_rejected_count", value=len(df_rejected))


def task_clean_vehicles(**context):
    import logging
    import pandas as pd
    from config.config import STAGING_DIR

    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: clean_vehicles ===")

    from transformation.clean_vehicles import clean_vehicles

    staged_path = STAGING_DIR / "vehicles_staged.csv"
    if not staged_path.exists():
        raise FileNotFoundError(f"Staged vehicles not found at {staged_path}.")

    df_staged = pd.read_csv(staged_path, low_memory=False)
    df_clean, df_rejected = clean_vehicles(df_staged)
    logger.info(
        "Vehicle cleaning complete: %d clean, %d rejected.",
        len(df_clean), len(df_rejected),
    )


def task_clean_casualties(**context):
    import logging
    import pandas as pd
    from config.config import STAGING_DIR

    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: clean_casualties ===")

    from transformation.clean_casualties import clean_casualties

    staged_path = STAGING_DIR / "casualties_staged.csv"
    if not staged_path.exists():
        raise FileNotFoundError(f"Staged casualties not found at {staged_path}.")

    df_staged = pd.read_csv(staged_path, low_memory=False)
    df_clean, df_rejected = clean_casualties(df_staged)
    logger.info(
        "Casualty cleaning complete: %d clean, %d rejected.",
        len(df_clean), len(df_rejected),
    )


def task_clean_weather(**context):
    """
    Load all weather Parquet files, clean them, and write a single
    consolidated CSV to data/cleaned/ and data/staging/.
    """
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: clean_weather ===")

    from transformation.clean_weather import clean_weather
    df = clean_weather()

    if df.empty:
        logger.warning(
            "Weather data is empty after cleaning. "
            "Weather columns will be NULL in the analytical mart. "
            "This is non-fatal — the pipeline will continue."
        )
    else:
        logger.info("Weather cleaning complete: %d rows, %d grid cells.",
                    len(df),
                    df[["grid_lat", "grid_lon"]].drop_duplicates().shape[0]
                    if "grid_lat" in df.columns else "?")


def task_join_accident_weather(**context):
    """
    Join cleaned accident records with nearest-hour weather observations.

    Matching strategy (documented in join_accident_weather.py):
    1. Snap accident lat/lon to 0.5° grid cell
    2. Round accident time to nearest integer hour
    3. LEFT JOIN — accidents without weather match keep NULL weather columns

    Output: data/cleaned/accidents_with_weather.csv
    """
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: join_accident_weather ===")

    from transformation.join_accident_weather import join_accident_weather
    df = join_accident_weather()

    matched = int(df["weather_matched"].sum()) if "weather_matched" in df.columns else "?"
    logger.info(
        "Weather join complete: %d total accidents, %s with weather data.",
        len(df), matched,
    )
    context["ti"].xcom_push(key="joined_row_count",    value=len(df))
    context["ti"].xcom_push(key="weather_match_count", value=matched)


def task_load_postgresql(**context):
    """
    Create PostgreSQL tables (if not exist) and load dimension + fact tables
    from the cleaned/joined data files.
    """
    import logging
    import psycopg2
    import re
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: load_postgresql ===")

    from config.config import get_db_connection_string

    sql_dir = _PROJECT_ROOT / "database"
    sql_files = [
        sql_dir / "schema.sql",
        sql_dir / "tables.sql",
        sql_dir / "indexes.sql",
    ]

    def _get_conn():
        return psycopg2.connect(get_db_connection_string())

    def _split_sql(text):
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        stmts = []
        for raw in text.split(";"):
            lines = [l for l in raw.splitlines()
                     if l.strip() and not l.strip().startswith("--")]
            s = "\n".join(lines).strip()
            if s:
                stmts.append(s)
        return stmts

    try:
        conn = _get_conn()
        conn.close()
        logger.info("Neon connection verified OK.")
    except psycopg2.OperationalError as exc:
        raise RuntimeError(
            f"Cannot connect to PostgreSQL/Neon: {exc}\n"
            "Check DATABASE_URL in .env — use the direct (non-pooler) connection string."
        ) from exc

    for sql_file in sql_files:
        if not sql_file.exists():
            logger.warning("SQL file not found: %s", sql_file)
            continue
        logger.info("Applying SQL file: %s", sql_file.name)
        statements = _split_sql(sql_file.read_text(encoding="utf-8"))
        ok = skipped = 0
        for stmt in statements:
            try:
                conn = _get_conn()
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute(stmt)
                conn.close()
                ok += 1
            except (psycopg2.errors.DuplicateTable,
                    psycopg2.errors.DuplicateObject):
                try:
                    conn.close()
                except Exception:
                    pass
                skipped += 1
            except psycopg2.Error as e:
                try:
                    conn.close()
                except Exception:
                    pass
                logger.debug("Skipped (%s): %.60s", type(e).__name__, stmt)
                skipped += 1
        logger.info("%s: %d applied, %d skipped", sql_file.name, ok, skipped)

    logger.info("Database schema applied successfully.")


def task_create_analytics_mart(**context):
    """
    Build the dimensional model and populate all tables:
      dim_severity, dim_date, dim_location, dim_road, dim_weather
      fact_accident
      accident_analytics_mart (denormalised analytical table)

    Safe to re-run: uses TRUNCATE + INSERT with ON CONFLICT handling.
    """
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: create_analytics_mart ===")

    from transformation.create_analytics_mart import build_analytics_mart
    build_analytics_mart()
    logger.info("Analytics mart built successfully.")


def task_run_data_quality_checks(**context):
    """
    Run all data-quality rules against the cleaned datasets.
    Produces:
      - Formatted quality report (logged to Airflow task logs)
      - JSON report saved to data/rejected/
      - ingestion_log entries in PostgreSQL

    Pipeline continues even if some LOG_WARN rules fail.
    Pipeline raises RuntimeError only if a FAIL_PIPELINE rule fails.
    """
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: run_data_quality_checks ===")

    from validation.data_quality import run_full_quality_report

    report = run_full_quality_report()
    overall = report.get("overall_status", "UNKNOWN")
    failed  = report.get("overall_checks_failed", 0)

    logger.info("Data quality check complete. Overall status: %s", overall)
    logger.info("Total checks failed: %d", failed)

    if report.get("pipeline_halt", False):
        raise RuntimeError(
            "Data quality FAIL_PIPELINE rule triggered. "
            "Review quality_report_combined.json in data/rejected/."
        )

    context["ti"].xcom_push(key="dq_overall_status",  value=overall)
    context["ti"].xcom_push(key="dq_checks_failed",   value=failed)


# ── DAG definition ─────────────────────────────────────────────────────────────

with DAG(
    dag_id="traffic_accident_pipeline",
    description=(
        "End-to-end UK traffic accident analytics pipeline: "
        "extract STATS19 + Open-Meteo → stage → clean → validate → "
        "PostgreSQL star schema → analytical mart"
    ),
    default_args=default_args,
    schedule=None,          # Manually triggered only
    catchup=False,
    max_active_runs=1,
    tags=["traffic", "analytics", "data-engineering"],
    doc_md="""
## Traffic Accident Analytics Pipeline

**Purpose:** Ingests UK STATS19 road accident data and Open-Meteo
weather data, transforms it through RAW → STAGING → CLEANED layers,
validates data quality, and loads a star-schema PostgreSQL database
plus an analytical data mart for the Streamlit dashboard.

**Trigger:** Manual only (`schedule=None`). Trigger from the Airflow
UI or with `airflow dags trigger traffic_accident_pipeline`.

**Idempotency:** Safe to re-run. Existing PostgreSQL records are
replaced via TRUNCATE + INSERT ON CONFLICT.

**Failure behaviour:**
- Each task retries 2 times with a 5-minute delay before failing.
- Data-quality LOG_WARN failures do not halt the pipeline.
- Data-quality FAIL_PIPELINE failures halt at the quality-check task.
""",
) as dag:

    # ── Entry point ───────────────────────────────────────────────────────────
    start = EmptyOperator(task_id="start")

    # ── Extraction (parallel) ─────────────────────────────────────────────────
    extract_accidents = PythonOperator(
        task_id="extract_accidents",
        python_callable=task_extract_accidents,
        retries=3,
        retry_delay=timedelta(minutes=2),
        doc_md=(
            "Downloads UK STATS19 collision CSV from data.dft.gov.uk. "
            "Falls back to manually placed file if download fails."
        ),
    )

    extract_vehicles = PythonOperator(
        task_id="extract_vehicles",
        python_callable=task_extract_vehicles,
        retries=3,
        retry_delay=timedelta(minutes=2),
        doc_md="Downloads UK STATS19 vehicle CSV.",
    )

    extract_casualties = PythonOperator(
        task_id="extract_casualties",
        python_callable=task_extract_casualties,
        retries=3,
        retry_delay=timedelta(minutes=2),
        doc_md="Downloads UK STATS19 casualty CSV.",
    )

    extract_weather = PythonOperator(
        task_id="extract_weather",
        python_callable=task_extract_weather,
        retries=2,
        retry_delay=timedelta(minutes=5),
        doc_md=(
            "Fetches hourly weather from Open-Meteo for all accident grid cells. "
            "Uses Parquet cache — API is only called for new/missing cells."
        ),
    )

    # ── Raw validation ────────────────────────────────────────────────────────
    validate_raw = PythonOperator(
        task_id="validate_raw_data",
        python_callable=task_validate_raw_data,
        doc_md="Checks raw files exist and are non-empty before staging begins.",
    )

    # ── Staging ───────────────────────────────────────────────────────────────
    create_staging = PythonOperator(
        task_id="create_staging",
        python_callable=task_create_staging,
        doc_md=(
            "Applies staging transformations: normalise column names, "
            "parse DD/MM/YYYY dates, HH:MM times, replace -1 missing codes."
        ),
    )

    # ── Cleaning (parallel) ───────────────────────────────────────────────────
    clean_accidents = PythonOperator(
        task_id="clean_accidents",
        python_callable=task_clean_accidents,
        doc_md=(
            "Cleans accident data: removes duplicates, rejects records with "
            "missing ID / invalid coords / bad date / invalid severity."
        ),
    )

    clean_vehicles = PythonOperator(
        task_id="clean_vehicles",
        python_callable=task_clean_vehicles,
        doc_md="Cleans vehicle data: removes duplicates, rejects orphan records.",
    )

    clean_casualties = PythonOperator(
        task_id="clean_casualties",
        python_callable=task_clean_casualties,
        doc_md="Cleans casualty data: removes duplicates, validates severity codes.",
    )

    clean_weather_task = PythonOperator(
        task_id="clean_weather",
        python_callable=task_clean_weather,
        doc_md=(
            "Consolidates weather Parquet cache into a single cleaned CSV. "
            "Non-fatal if weather data is unavailable."
        ),
    )

    # ── Join ──────────────────────────────────────────────────────────────────
    join_weather = PythonOperator(
        task_id="join_accident_weather",
        python_callable=task_join_accident_weather,
        doc_md=(
            "Joins cleaned accidents with hourly weather via grid-snap + "
            "nearest-hour matching. Accidents without weather data keep "
            "NULL weather columns (left join — no accidents are lost)."
        ),
    )

    # ── PostgreSQL load ───────────────────────────────────────────────────────
    load_pg = PythonOperator(
        task_id="load_postgresql",
        python_callable=task_load_postgresql,
        doc_md="Creates/updates PostgreSQL schema (schema.sql, tables.sql, indexes.sql).",
    )

    # ── Analytical mart ───────────────────────────────────────────────────────
    build_mart = PythonOperator(
        task_id="create_analytics_mart",
        python_callable=task_create_analytics_mart,
        doc_md=(
            "Builds star-schema dimensions and fact table, then populates "
            "accident_analytics_mart for dashboard queries."
        ),
    )

    # ── Quality checks ────────────────────────────────────────────────────────
    dq_checks = PythonOperator(
        task_id="run_data_quality_checks",
        python_callable=task_run_data_quality_checks,
        doc_md=(
            "Runs 16 validation rules across accidents/vehicles/casualties/weather. "
            "Saves JSON quality report. Logs to ingestion_log table."
        ),
    )

    # ── Exit point ────────────────────────────────────────────────────────────
    pipeline_complete = EmptyOperator(task_id="pipeline_complete")

    # ── Task dependencies (the pipeline flow) ─────────────────────────────────
    #
    # Extraction runs in parallel, then converges at validate_raw
    start >> [extract_accidents, extract_vehicles, extract_casualties, extract_weather]
    [extract_accidents, extract_vehicles, extract_casualties, extract_weather] >> validate_raw

    # Staging runs after raw validation
    validate_raw >> create_staging

    # Cleaning runs in parallel after staging
    create_staging >> [clean_accidents, clean_vehicles, clean_casualties, clean_weather_task]

    # Join requires clean accidents AND clean weather
    [clean_accidents, clean_weather_task] >> join_weather

    # vehicles and casualties just need to be cleaned before DB load
    [join_weather, clean_vehicles, clean_casualties] >> load_pg

    # Mart build requires DB to be set up
    load_pg >> build_mart

    # Quality checks run after mart is populated
    build_mart >> dq_checks

    # Done
    dq_checks >> pipeline_complete
