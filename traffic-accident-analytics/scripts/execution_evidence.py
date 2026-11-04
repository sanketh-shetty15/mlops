"""
scripts/execution_evidence.py
-------------------------------
Produces a clean, formatted execution evidence report — suitable for
copying directly into a PPT slide or academic report.

Run with:
    python scripts/execution_evidence.py

The output matches the terminal screenshot format used in the
Data Engineering & MLOps project presentation.
"""

import sys
import time
import psycopg2
import pandas as pd
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config import get_db_connection_string, get_logger, CLEANED_DIR, REJECTED_DIR

logger = get_logger("execution_evidence")

SEP  = "=" * 72
THIN = "-" * 72


def _print(line=""):
    print(line)


def _sep():
    _print(SEP)


def _thin():
    _print(THIN)


def _conn():
    return psycopg2.connect(get_db_connection_string())


def _query(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def _scalar(conn, sql, default=0):
    rows = _query(conn, sql)
    return rows[0][0] if rows and rows[0][0] is not None else default


# ── Step 1: Ingestion Evidence ─────────────────────────────────────────────────

def step1_ingestion():
    _print()
    _print("[Step 1/4] Ingesting Raw Data Sources...")

    from config.config import (
        RAW_ACCIDENTS_DIR, RAW_VEHICLES_DIR, RAW_CASUALTIES_DIR,
        RAW_WEATHER_DIR,
        ACCIDENTS_FILENAME, VEHICLES_FILENAME, CASUALTIES_FILENAME,
    )

    sources = {
        "accidents":  RAW_ACCIDENTS_DIR  / ACCIDENTS_FILENAME,
        "vehicles":   RAW_VEHICLES_DIR   / VEHICLES_FILENAME,
        "casualties": RAW_CASUALTIES_DIR / CASUALTIES_FILENAME,
    }

    total_rows = 0
    for name, path in sources.items():
        if not path.exists():
            alts = list(path.parent.glob("*.csv"))
            if alts:
                path = alts[0]
        if path.exists():
            df = pd.read_csv(path, low_memory=False)
            size_mb = path.stat().st_size / (1024 * 1024)
            _print(f"  [Ingestion]  {name:<12} CSV loaded  →  "
                   f"{len(df):>7,} rows  ({size_mb:.1f} MB)")
            if name == "accidents":
                total_rows = len(df)
        else:
            _print(f"  [Ingestion]  {name:<12} CSV NOT FOUND at {path}")

    weather_files = list(RAW_WEATHER_DIR.glob("weather_*.parquet"))
    if weather_files:
        _print(f"  [Ingestion]  weather       cache loaded  →  "
               f"{len(weather_files):>7,} Parquet files  (grid-snapped 0.5°)")

    _print(f"  [Ingestion]  Raw accident dataset: {total_rows:,} total collision rows")


# ── Step 2: Cleaning & Validation Evidence ────────────────────────────────────

def step2_cleaning():
    _print()
    _print("[Step 2/4] Executing Data Quality Rules & Validation...")

    from config.config import CLEANED_DIR, REJECTED_DIR

    # Accidents
    acc_clean = CLEANED_DIR / "accidents_cleaned.csv"
    acc_rej   = REJECTED_DIR / "accidents_rejected.csv"
    acc_wx    = CLEANED_DIR  / "accidents_with_weather.csv"

    if acc_clean.exists():
        df_clean = pd.read_csv(acc_clean, low_memory=False)
        _print(f"  [Cleaning]   Applied 11 validation rules  "
               f"(accident_id, lat/lon, date, severity, counts)")
    else:
        _print("  [Cleaning]   accidents_cleaned.csv not found — run pipeline first")
        return

    rejected = 0
    if acc_rej.exists():
        df_rej = pd.read_csv(acc_rej, low_memory=False)
        rejected = len(df_rej)
        reasons = df_rej["rejection_reason"].value_counts()
        for reason, count in reasons.items():
            _print(f"  [Cleaning]   Rejected {count:>5,} rows  →  {reason}")

    _print(f"  [Cleaning]   Saved {len(df_clean):,} clean accidents  "
           f"→  data/cleaned/accidents_cleaned.csv")

    # Weather join
    if acc_wx.exists():
        df_wx = pd.read_csv(acc_wx, low_memory=False)
        matched = df_wx["weather_matched"].sum() if "weather_matched" in df_wx.columns else 0
        pct = 100 * matched / len(df_wx) if len(df_wx) else 0
        _print(f"  [WeatherJoin] Matched {matched:,}/{len(df_wx):,} accidents "
               f"to hourly weather ({pct:.1f}%)  →  data/cleaned/accidents_with_weather.csv")


# ── Step 3: Star Schema & Mart Build Evidence ─────────────────────────────────

def step3_database():
    _print()
    _print("[Step 3/4] Star Schema Data Warehouse & Analytical Mart Build...")

    try:
        conn = _conn()
    except Exception as exc:
        _print(f"  [Transform]  PostgreSQL connection failed: {exc}")
        return None

    tables = {
        "dim_severity":           ("Dimension",  "severity_id"),
        "dim_date":               ("Dimension",  "date_id"),
        "dim_location":           ("Dimension",  "location_id"),
        "dim_road":               ("Dimension",  "road_id"),
        "dim_weather":            ("Dimension",  "weather_id"),
        "fact_accident":          ("Fact Table", "accident_id"),
        "rejected_records":       ("Audit",      "rejected_id"),
        "accident_analytics_mart":("Data Mart",  "accident_index"),
        "ingestion_log":          ("Metadata",   "id"),
    }

    counts = {}
    for table, (schema_type, key_col) in tables.items():
        try:
            count = _scalar(conn, f"SELECT COUNT(*) FROM {table};")
            counts[table] = count
        except Exception:
            counts[table] = -1

    _print(f"  [Transform]  Populated PostgreSQL Star Schema  "
           f"→  Neon Cloud (ep-wispy-bar-axiek9h6)")
    _print(f"  [Transform]  Dimensions: "
           f"severity={counts.get('dim_severity',0)}, "
           f"date={counts.get('dim_date',0)}, "
           f"location={counts.get('dim_location',0):,}, "
           f"road={counts.get('dim_road',0)}, "
           f"weather={counts.get('dim_weather',0)}")
    _print(f"  [Transform]  Fact Table: "
           f"{counts.get('fact_accident',0):,} rows  "
           f"| Analytical Mart: "
           f"{counts.get('accident_analytics_mart',0):,} rows")

    conn.close()
    return counts


# ── Step 4: Data Quality Report Evidence ─────────────────────────────────────

def step4_quality():
    _print()
    _print("[Step 4/4] Data Quality Checks & Validation Report...")

    reports = list(REJECTED_DIR.glob("quality_report_accidents_*.json"))
    if reports:
        import json
        latest = max(reports, key=lambda p: p.stat().st_mtime)
        with open(latest) as f:
            report = json.load(f)

        passed = report.get("checks_passed", 0)
        failed = report.get("checks_failed", 0)
        total  = report.get("total_records", 0)

        _print(f"  [Quality]    Dataset: ACCIDENTS  |  "
               f"Total Records: {total:,}")
        _print(f"  [Quality]    Checks Passed: {passed}  |  "
               f"Checks Failed: {failed}  |  Overall Status: "
               f"{'PASS' if failed == 0 else 'WARN'}")

        for r in report.get("results", []):
            status = "PASS" if r["passed"] else "FAIL"
            _print(f"  [Quality]    [{status}] {r['rule']:<42}  {r['message']}")
    else:
        _print("  [Quality]    No quality report found — run pipeline first")


# ── Database Verification Table ───────────────────────────────────────────────

def db_verification(counts: dict):
    _print()
    _sep()
    _print("  TRAFFIC ACCIDENT DATA WAREHOUSE RECORD VERIFICATION (Neon PostgreSQL)")
    _sep()

    col_w = [32, 12, 20, 12]
    header = (
        f"  {'Table Name':<{col_w[0]}}"
        f"| {'Schema Type':<{col_w[1]}}"
        f"| {'Key Column':<{col_w[2]}}"
        f"| {'Row Count':>{col_w[3]}}"
    )
    _print(header)
    _thin()

    rows_data = [
        ("ingestion_log",            "Metadata",   "id",              counts.get("ingestion_log", 0)),
        ("dim_severity",             "Dimension",  "severity_id",     counts.get("dim_severity", 0)),
        ("dim_date",                 "Dimension",  "date_id",         counts.get("dim_date", 0)),
        ("dim_location",             "Dimension",  "location_id",     counts.get("dim_location", 0)),
        ("dim_road",                 "Dimension",  "road_id",         counts.get("dim_road", 0)),
        ("dim_weather",              "Dimension",  "weather_id",      counts.get("dim_weather", 0)),
        ("fact_accident",            "Fact Table", "accident_id",     counts.get("fact_accident", 0)),
        ("rejected_records",         "Audit",      "rejected_id",     counts.get("rejected_records", 0)),
        ("accident_analytics_mart",  "Data Mart",  "accident_index",  counts.get("accident_analytics_mart", 0)),
    ]

    for table, schema_type, key_col, row_count in rows_data:
        rc = f"{row_count:,}" if row_count >= 0 else "N/A"
        _print(
            f"  {table:<{col_w[0]}}"
            f"| {schema_type:<{col_w[1]}}"
            f"| {key_col:<{col_w[2]}}"
            f"| {rc:>{col_w[3]}}"
        )


# ── Funnel Summary ────────────────────────────────────────────────────────────

def funnel_summary(counts: dict):
    from config.config import RAW_ACCIDENTS_DIR, ACCIDENTS_FILENAME

    raw_path = RAW_ACCIDENTS_DIR / ACCIDENTS_FILENAME
    raw_rows = 0
    if raw_path.exists():
        raw_rows = sum(1 for _ in open(raw_path, encoding="utf-8")) - 1

    clean_path = CLEANED_DIR / "accidents_cleaned.csv"
    clean_rows = 0
    if clean_path.exists():
        clean_rows = sum(1 for _ in open(clean_path, encoding="utf-8")) - 1

    mart_rows = counts.get("accident_analytics_mart", 0)
    weather_rows = counts.get("dim_weather", 0)

    _print()
    _sep()
    _print(
        f"  [Funnel Summary]  "
        f"{raw_rows:,} Raw  →  "
        f"{clean_rows:,} Cleaned  →  "
        f"{mart_rows:,} in Analytical Mart  "
        f"| Weather Conditions: {weather_rows}"
    )
    _sep()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    _sep()
    _print("  TRAFFIC ACCIDENT SEVERITY ANALYTICS")
    _print("  DATA ENGINEERING & MLOPS EXECUTION EVIDENCE")
    _print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _print(f"  Student: Sanketh H R  |  USN: 1CR23CI047  |  CMRIT Bengaluru")
    _sep()

    step1_ingestion()
    _print()
    step2_cleaning()
    _print()
    counts = step3_database()
    _print()
    step4_quality()

    if counts:
        db_verification(counts)
        funnel_summary(counts)
    else:
        _print()
        _sep()
        _print("  [Warning] Could not connect to PostgreSQL — skipping DB verification.")
        _print("  Run: python scripts/run_pipeline.py  to populate the database first.")
        _sep()

    _print()


if __name__ == "__main__":
    main()
