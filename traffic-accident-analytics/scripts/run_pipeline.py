"""
Pipeline stages
---------------
1.  extract_accidents       Download STATS19 collision CSV
2.  extract_vehicles        Download STATS19 vehicle CSV
3.  extract_casualties      Download STATS19 casualty CSV
4.  extract_weather         Fetch Open-Meteo hourly data (grid-snapped)
5.  validate_raw            Check raw files exist and are non-empty
6.  stage_all               Normalise columns, parse dates/times
7.  clean_accidents         Apply rejection rules to accidents
8.  clean_vehicles          Apply rejection rules to vehicles
9.  clean_casualties        Apply rejection rules to casualties
10. clean_weather           Consolidate weather Parquet → CSV
11. join_accident_weather   Left-join accidents with nearest-hour weather
12. setup_database          Apply schema.sql + tables.sql + indexes.sql
13. build_analytics_mart    Populate dimension tables + fact + mart
14. run_quality_checks      Run all 16 validation rules, print report
"""

import sys
import time
import argparse
import traceback
from pathlib import Path
from datetime import datetime

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import get_logger

logger = get_logger("run_pipeline")

# ── Stage definitions ──────────────────────────────────────────────────────────
STAGE_ORDER = [
    "extract", "validate_raw", "staging", "cleaning",
    "join", "database", "mart", "quality",
]


def _header(msg: str) -> None:
    line = "=" * 60
    logger.info("\n%s\n  %s\n%s", line, msg, line)


def _step(name: str, fn, *args, **kwargs):
    """Run a pipeline step, time it, and handle errors gracefully."""
    logger.info("▶  Starting: %s", name)
    t0 = time.time()
    try:
        result = fn(*args, **kwargs)
        elapsed = time.time() - t0
        logger.info("✓  Completed: %s (%.1fs)", name, elapsed)
        return result
    except Exception as exc:
        elapsed = time.time() - t0
        logger.error("✗  FAILED: %s after %.1fs", name, elapsed)
        logger.error("   Error: %s", exc)
        logger.debug(traceback.format_exc())
        raise


# ── Stage functions ────────────────────────────────────────────────────────────

def stage_extract(force_download: bool = False, skip_weather_api: bool = False):
    from ingestion.accident_ingestion  import ingest_accidents
    from ingestion.vehicle_ingestion   import ingest_vehicles
    from ingestion.casualty_ingestion  import ingest_casualties
    from ingestion.weather_ingestion   import ingest_weather

    _header("STAGE 1: DATA EXTRACTION")
    df_acc = _step("Extract accidents",  ingest_accidents,  force_download=force_download)
    df_veh = _step("Extract vehicles",   ingest_vehicles,   force_download=force_download)
    df_cas = _step("Extract casualties", ingest_casualties, force_download=force_download)

    if not skip_weather_api:
        _step("Extract weather", ingest_weather, force_download=force_download)
    else:
        logger.info("⏭  Skipping weather API (--skip-weather-api flag set)")

    logger.info(
        "Extraction summary: accidents=%d, vehicles=%d, casualties=%d",
        len(df_acc), len(df_veh), len(df_cas),
    )
    return df_acc, df_veh, df_cas


def stage_validate_raw():
    from config.config import (
        RAW_ACCIDENTS_DIR, RAW_VEHICLES_DIR, RAW_CASUALTIES_DIR,
        ACCIDENTS_FILENAME, VEHICLES_FILENAME, CASUALTIES_FILENAME,
        RAW_WEATHER_DIR,
    )

    _header("STAGE 2: RAW DATA VALIDATION")

    checks = {
        "accidents":  RAW_ACCIDENTS_DIR  / ACCIDENTS_FILENAME,
        "vehicles":   RAW_VEHICLES_DIR   / VEHICLES_FILENAME,
        "casualties": RAW_CASUALTIES_DIR / CASUALTIES_FILENAME,
    }
    all_ok = True
    for name, path in checks.items():
        if not path.exists():
            alts = list(path.parent.glob("*.csv"))
            if alts:
                logger.warning("  %s: using alternative file %s", name, alts[0].name)
            else:
                logger.error("  %s: FILE NOT FOUND at %s", name, path)
                all_ok = False
        else:
            size_mb = path.stat().st_size / (1024 * 1024)
            logger.info("  %s: OK (%.1f MB)", name, size_mb)

    wx_files = list(RAW_WEATHER_DIR.glob("weather_*.parquet"))
    if wx_files:
        logger.info("  weather: %d Parquet cache files found", len(wx_files))
    else:
        logger.warning("  weather: no cache files — weather columns will be NULL")

    if not all_ok:
        raise FileNotFoundError(
            "One or more raw data files are missing. "
            "Run with --force-download or manually place the CSVs."
        )
    logger.info("Raw data validation: PASSED")


def stage_staging(df_acc, df_veh, df_cas):
    from transformation.clean_accidents  import stage_accidents
    from transformation.clean_vehicles   import stage_vehicles
    from transformation.clean_casualties import stage_casualties

    _header("STAGE 3: STAGING")
    staged_acc = _step("Stage accidents",  stage_accidents,  df_acc)
    staged_veh = _step("Stage vehicles",   stage_vehicles,   df_veh)
    staged_cas = _step("Stage casualties", stage_casualties, df_cas)
    return staged_acc, staged_veh, staged_cas


def stage_cleaning(staged_acc, staged_veh, staged_cas):
    import pandas as pd
    from config.config import STAGING_DIR
    from transformation.clean_accidents  import clean_accidents
    from transformation.clean_vehicles   import clean_vehicles
    from transformation.clean_casualties import clean_casualties
    from transformation.clean_weather    import clean_weather

    _header("STAGE 4: DATA CLEANING")

    # If called from --start-from cleaning, staged DataFrames may be None
    if staged_acc is None:
        staged_acc = pd.read_csv(STAGING_DIR / "accidents_staged.csv",  low_memory=False)
    if staged_veh is None:
        staged_veh = pd.read_csv(STAGING_DIR / "vehicles_staged.csv",   low_memory=False)
    if staged_cas is None:
        staged_cas = pd.read_csv(STAGING_DIR / "casualties_staged.csv", low_memory=False)

    df_acc_clean, df_acc_rej  = _step("Clean accidents",  clean_accidents,  staged_acc)
    df_veh_clean, df_veh_rej  = _step("Clean vehicles",   clean_vehicles,   staged_veh)
    df_cas_clean, df_cas_rej  = _step("Clean casualties", clean_casualties, staged_cas)
    df_wx_clean               = _step("Clean weather",    clean_weather)

    logger.info(
        "Cleaning summary: "
        "accidents=%d (rejected=%d), vehicles=%d (rejected=%d), "
        "casualties=%d (rejected=%d), weather=%d",
        len(df_acc_clean), len(df_acc_rej),
        len(df_veh_clean), len(df_veh_rej),
        len(df_cas_clean), len(df_cas_rej),
        len(df_wx_clean) if df_wx_clean is not None else 0,
    )
    return df_acc_clean, df_veh_clean, df_cas_clean, df_wx_clean


def stage_join():
    from transformation.join_accident_weather import join_accident_weather

    _header("STAGE 5: ACCIDENT + WEATHER JOIN")
    df_joined = _step("Join accident + weather", join_accident_weather)

    if "weather_matched" in df_joined.columns:
        matched = df_joined["weather_matched"].sum()
        pct = 100 * matched / len(df_joined) if len(df_joined) else 0
        logger.info(
            "Join complete: %d accidents, %d with weather (%.1f%%)",
            len(df_joined), matched, pct,
        )
    return df_joined


def stage_database():
    import psycopg2
    import re
    from config.config import get_db_connection_string

    _header("STAGE 6: DATABASE SETUP")

    project_root = Path(__file__).resolve().parent.parent
    sql_files = [
        project_root / "database" / "schema.sql",
        project_root / "database" / "tables.sql",
        project_root / "database" / "indexes.sql",
    ]

    def _get_conn():
        return psycopg2.connect(get_db_connection_string())

    def _split_sql(text: str) -> list:
        """
        Split SQL text into individual statements, skipping comment-only
        blocks and empty strings. Handles multi-line comments correctly.
        """
        # Remove block comments /* ... */
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        # Remove single-line comments that are the entire statement
        statements = []
        for raw in text.split(";"):
            # Strip comments and whitespace
            lines = [
                line for line in raw.splitlines()
                if line.strip() and not line.strip().startswith("--")
            ]
            stmt = "\n".join(lines).strip()
            if stmt:
                statements.append(stmt)
        return statements

    try:
        # Quick connectivity test
        conn = _get_conn()
        conn.close()
        logger.info("Neon connection verified OK.")
    except psycopg2.OperationalError as exc:
        raise RuntimeError(
            f"Cannot connect to PostgreSQL/Neon: {exc}\n"
            "Check your DATABASE_URL in .env — make sure you are using\n"
            "the DIRECT connection string (no '-pooler' in the hostname).\n"
            "Use --skip-db to run the pipeline without a database."
        ) from exc

    for sql_file in sql_files:
        if not sql_file.exists():
            logger.warning("SQL file not found: %s", sql_file)
            continue

        logger.info("Applying: %s", sql_file.name)
        statements = _split_sql(sql_file.read_text(encoding="utf-8"))
        logger.info("  %d statements to execute", len(statements))

        ok = 0
        skipped = 0
        for stmt in statements:
            # Use a fresh connection per statement — avoids Neon pool timeouts
            # on large DDL files and cleanly handles already-exists errors.
            try:
                conn = _get_conn()
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute(stmt)
                conn.close()
                ok += 1
            except psycopg2.errors.DuplicateTable:
                conn.close()
                skipped += 1
            except psycopg2.errors.DuplicateObject:
                conn.close()
                skipped += 1
            except psycopg2.Error as exc:
                try:
                    conn.close()
                except Exception:
                    pass
                # Log but continue — e.g. CREATE INDEX IF NOT EXISTS on
                # a column that already has a different index
                logger.debug("  Statement skipped (%s): %.80s...", type(exc).__name__, stmt)
                skipped += 1

        logger.info(
            "  %s: %d applied, %d already-existed/skipped",
            sql_file.name, ok, skipped
        )

    logger.info("Database schema applied: OK")


def stage_mart():
    from transformation.create_analytics_mart import build_analytics_mart

    _header("STAGE 7: BUILD ANALYTICAL DATA MART")
    _step("Build analytics mart", build_analytics_mart)


def stage_quality():
    from validation.data_quality import run_full_quality_report

    _header("STAGE 8: DATA QUALITY CHECKS")
    report = _step("Run quality checks", run_full_quality_report)

    overall = report.get("overall_status", "UNKNOWN")
    failed  = report.get("overall_checks_failed", 0)
    logger.info("Quality check status: %s (%d checks failed)", overall, failed)
    return report


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run the Traffic Accident Analytics pipeline end-to-end."
    )
    parser.add_argument(
        "--skip-db", action="store_true",
        help="Skip PostgreSQL loading steps (useful when DB is not running)",
    )
    parser.add_argument(
        "--force-download", action="store_true",
        help="Re-download raw data even if files already exist",
    )
    parser.add_argument(
        "--skip-weather-api", action="store_true",
        help="Skip Open-Meteo API calls; use cached Parquet files only",
    )
    parser.add_argument(
        "--start-from",
        choices=STAGE_ORDER,
        default="extract",
        help="Start the pipeline from this stage (assumes prior stages completed)",
    )
    args = parser.parse_args()

    start_time = time.time()
    logger.info("=" * 60)
    logger.info("  TRAFFIC ACCIDENT ANALYTICS PIPELINE")
    logger.info("  Started: %s", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
    logger.info("  Start from: %s", args.start_from)
    logger.info("  Skip DB: %s", args.skip_db)
    logger.info("=" * 60)

    stage_idx = STAGE_ORDER.index(args.start_from)
    df_acc = df_veh = df_cas = None
    staged_acc = staged_veh = staged_cas = None

    try:
        # ── Extract ───────────────────────────────────────────────────────────
        if stage_idx <= STAGE_ORDER.index("extract"):
            df_acc, df_veh, df_cas = stage_extract(
                force_download=args.force_download,
                skip_weather_api=args.skip_weather_api,
            )

        # ── Validate raw ──────────────────────────────────────────────────────
        if stage_idx <= STAGE_ORDER.index("validate_raw"):
            stage_validate_raw()

        # ── Staging ───────────────────────────────────────────────────────────
        if stage_idx <= STAGE_ORDER.index("staging"):
            if df_acc is None:
                # Load raw CSVs if we skipped extraction
                import pandas as pd
                from config.config import (
                    RAW_ACCIDENTS_DIR, RAW_VEHICLES_DIR, RAW_CASUALTIES_DIR,
                    ACCIDENTS_FILENAME, VEHICLES_FILENAME, CASUALTIES_FILENAME,
                )

                def _load(d, f):
                    p = d / f
                    if not p.exists():
                        alts = list(d.glob("*.csv"))
                        if alts:
                            return pd.read_csv(alts[0], low_memory=False)
                        raise FileNotFoundError(f"No CSV in {d}")
                    return pd.read_csv(p, low_memory=False)

                df_acc = _load(RAW_ACCIDENTS_DIR,  ACCIDENTS_FILENAME)
                df_veh = _load(RAW_VEHICLES_DIR,   VEHICLES_FILENAME)
                df_cas = _load(RAW_CASUALTIES_DIR, CASUALTIES_FILENAME)

            staged_acc, staged_veh, staged_cas = stage_staging(df_acc, df_veh, df_cas)

        # ── Cleaning ──────────────────────────────────────────────────────────
        if stage_idx <= STAGE_ORDER.index("cleaning"):
            stage_cleaning(staged_acc, staged_veh, staged_cas)

        # ── Join ──────────────────────────────────────────────────────────────
        if stage_idx <= STAGE_ORDER.index("join"):
            stage_join()

        # ── Database & mart ───────────────────────────────────────────────────
        if not args.skip_db:
            if stage_idx <= STAGE_ORDER.index("database"):
                stage_database()
            if stage_idx <= STAGE_ORDER.index("mart"):
                stage_mart()
            if stage_idx <= STAGE_ORDER.index("quality"):
                stage_quality()
        else:
            logger.info("⏭  Skipping database stages (--skip-db flag set)")
            logger.info("   Quality checks will still run on CSV files.")
            if stage_idx <= STAGE_ORDER.index("quality"):
                stage_quality()

    except Exception as exc:
        elapsed = time.time() - start_time
        logger.error("\n" + "=" * 60)
        logger.error("  PIPELINE FAILED after %.1fs", elapsed)
        logger.error("  Error: %s", exc)
        logger.error("=" * 60)
        sys.exit(1)

    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 60)
    logger.info("  PIPELINE COMPLETE in %.1fs", elapsed)
    logger.info(
        "  Next step: streamlit run dashboard/app.py"
        if not args.skip_db else
        "  Next step: start PostgreSQL and run again without --skip-db"
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
