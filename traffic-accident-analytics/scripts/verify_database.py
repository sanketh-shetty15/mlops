"""
scripts/verify_database.py
----------------------------
Verifies that the PostgreSQL database has been populated correctly
after a pipeline run.

Prints a structured health report showing:
  - Connection status
  - Table existence
  - Row counts in every table
  - Sample data from the analytical mart
  - Top 5 accidents by severity
  - Index list
  - Any rejected records summary

Usage
-----
    python scripts/verify_database.py

    # Show detailed sample rows
    python scripts/verify_database.py --verbose

    # Export report to a text file
    python scripts/verify_database.py --output report.txt
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import get_db_connection_string, get_logger

logger = get_logger("verify_database")


def _connect():
    """Open a PostgreSQL connection or exit with a clear error."""
    try:
        import psycopg2
        conn = psycopg2.connect(get_db_connection_string())
        return conn
    except Exception as exc:
        print(f"\n[ERROR] Cannot connect to PostgreSQL: {exc}")
        print("\nSteps to fix:")
        print("  1. Ensure PostgreSQL is running")
        print("  2. Check .env file: POSTGRES_HOST, PORT, DB, USER, PASSWORD")
        print("  3. Run: python scripts/run_pipeline.py")
        sys.exit(1)


def _query(conn, sql: str, params=None) -> list:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _scalar(conn, sql: str, params=None, default=None):
    rows = _query(conn, sql, params)
    return rows[0][0] if rows and rows[0][0] is not None else default


def run_verification(verbose: bool = False) -> dict:
    report_lines = []

    def _p(line=""):
        report_lines.append(line)
        print(line)

    sep   = "=" * 65
    thin  = "-" * 65

    _p(sep)
    _p(f"  DATABASE VERIFICATION REPORT")
    _p(f"  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    _p(sep)

    conn = _connect()
    _p(f"\n  ✓ Connected to PostgreSQL successfully")

    # ── Table existence and row counts ─────────────────────────────────────────
    tables = [
        "ingestion_log",
        "dim_severity",
        "dim_date",
        "dim_location",
        "dim_road",
        "dim_weather",
        "fact_accident",
        "rejected_records",
        "accident_analytics_mart",
    ]

    _p(f"\n{thin}")
    _p("  TABLE ROW COUNTS")
    _p(thin)
    _p(f"  {'Table':<35} {'Rows':>10}  Status")
    _p(thin)

    table_counts = {}
    all_tables_ok = True

    for table in tables:
        try:
            count = _scalar(
                conn,
                f"SELECT COUNT(*) FROM {table};",
                default=0,
            )
            table_counts[table] = count
            status = "✓" if count > 0 else "⚠ EMPTY"
            if count == 0 and table not in ("ingestion_log", "rejected_records"):
                all_tables_ok = False
            _p(f"  {table:<35} {count:>10,}  {status}")
        except Exception as exc:
            table_counts[table] = -1
            all_tables_ok = False
            _p(f"  {table:<35} {'MISSING':>10}  ✗ ({exc})")

    # ── Analytics mart key fields ──────────────────────────────────────────────
    mart_count = table_counts.get("accident_analytics_mart", 0)

    if mart_count > 0:
        _p(f"\n{thin}")
        _p("  ANALYTICS MART SUMMARY")
        _p(thin)

        # Year range
        try:
            rows = _query(conn,
                "SELECT MIN(year), MAX(year), COUNT(DISTINCT year) "
                "FROM accident_analytics_mart WHERE year IS NOT NULL;")
            if rows:
                _p(f"  Year range         : {rows[0][0]} – {rows[0][1]}  "
                   f"({rows[0][2]} distinct year(s))")
        except Exception:
            pass

        # Severity breakdown
        try:
            rows = _query(conn,
                "SELECT severity_label, COUNT(*) AS n "
                "FROM accident_analytics_mart "
                "WHERE severity_label IS NOT NULL "
                "GROUP BY severity_label ORDER BY severity_label;")
            _p("  Severity breakdown :")
            for r in rows:
                _p(f"    {r[0]:<12} {r[1]:>8,}")
        except Exception:
            pass

        # Weather match rate
        try:
            pct = _scalar(conn,
                "SELECT ROUND(100.0 * SUM(CASE WHEN weather_matched THEN 1 ELSE 0 END)"
                " / NULLIF(COUNT(*),0), 1) FROM accident_analytics_mart;",
                default=0.0)
            _p(f"  Weather matched    : {pct}%")
        except Exception:
            pass

        # Road types present
        try:
            rows = _query(conn,
                "SELECT road_type_name, COUNT(*) AS n "
                "FROM accident_analytics_mart "
                "WHERE road_type_name IS NOT NULL "
                "GROUP BY road_type_name ORDER BY n DESC LIMIT 5;")
            _p("  Top road types     :")
            for r in rows:
                _p(f"    {str(r[0]):<30} {r[1]:>8,}")
        except Exception:
            pass

        # Hour distribution (peak hours)
        try:
            rows = _query(conn,
                "SELECT accident_hour, COUNT(*) AS n "
                "FROM accident_analytics_mart "
                "WHERE accident_hour IS NOT NULL "
                "GROUP BY accident_hour ORDER BY n DESC LIMIT 3;")
            _p("  Peak accident hours:")
            for r in rows:
                _p(f"    {r[0]:02d}:00               {r[1]:>8,}")
        except Exception:
            pass

    # ── Dimension table spot checks ────────────────────────────────────────────
    _p(f"\n{thin}")
    _p("  DIMENSION TABLE SPOT CHECKS")
    _p(thin)

    # dim_severity
    try:
        rows = _query(conn, "SELECT severity_id, severity_name FROM dim_severity ORDER BY severity_id;")
        _p(f"  dim_severity: {', '.join(f'{r[0]}={r[1]}' for r in rows)}")
    except Exception as e:
        _p(f"  dim_severity: FAILED ({e})")

    # dim_date
    try:
        rows = _query(conn,
            "SELECT MIN(full_date), MAX(full_date) FROM dim_date;")
        _p(f"  dim_date range: {rows[0][0]} → {rows[0][1]}")
    except Exception as e:
        _p(f"  dim_date: FAILED ({e})")

    # dim_weather
    try:
        count = _scalar(conn, "SELECT COUNT(*) FROM dim_weather;", default=0)
        _p(f"  dim_weather: {count} distinct weather codes")
    except Exception as e:
        _p(f"  dim_weather: FAILED ({e})")

    # ── Rejected records ───────────────────────────────────────────────────────
    rej_count = table_counts.get("rejected_records", 0)
    if rej_count > 0:
        _p(f"\n{thin}")
        _p("  REJECTED RECORDS SUMMARY")
        _p(thin)
        try:
            rows = _query(conn,
                "SELECT source, rejection_reason, COUNT(*) AS n "
                "FROM rejected_records "
                "GROUP BY source, rejection_reason "
                "ORDER BY n DESC LIMIT 10;")
            for r in rows:
                _p(f"  [{r[0]}] {str(r[1]):<40} {r[2]:>6,} rows")
        except Exception as e:
            _p(f"  Could not query rejected_records: {e}")

    # ── Indexes ────────────────────────────────────────────────────────────────
    if verbose:
        _p(f"\n{thin}")
        _p("  INDEXES")
        _p(thin)
        try:
            rows = _query(conn,
                "SELECT tablename, indexname FROM pg_indexes "
                "WHERE schemaname = 'public' "
                "AND tablename IN ("
                "  'accident_analytics_mart','fact_accident',"
                "  'dim_date','dim_location','ingestion_log'"
                ") ORDER BY tablename, indexname;")
            for r in rows:
                _p(f"  {r[0]:<30} {r[1]}")
        except Exception as e:
            _p(f"  Could not list indexes: {e}")

    # ── Ingestion log ──────────────────────────────────────────────────────────
    log_count = table_counts.get("ingestion_log", 0)
    if log_count > 0:
        _p(f"\n{thin}")
        _p("  RECENT INGESTION LOG (last 5 entries)")
        _p(thin)
        try:
            rows = _query(conn,
                "SELECT source_name, status, row_count, "
                "extraction_timestamp::TEXT "
                "FROM ingestion_log "
                "ORDER BY extraction_timestamp DESC LIMIT 5;")
            _p(f"  {'Source':<30} {'Status':<10} {'Rows':>8}  Timestamp")
            for r in rows:
                _p(f"  {str(r[0]):<30} {str(r[1]):<10} {str(r[2] or ''):>8}  {r[3]}")
        except Exception as e:
            _p(f"  Could not query ingestion_log: {e}")

    # ── Overall status ─────────────────────────────────────────────────────────
    _p(f"\n{sep}")
    if all_tables_ok and mart_count > 0:
        _p("  ✓ DATABASE VERIFICATION: PASSED")
        _p(f"  {mart_count:,} records in accident_analytics_mart — ready for dashboard")
        _p(f"\n  Run dashboard:")
        _p("    streamlit run dashboard/app.py")
    else:
        _p("  ⚠ DATABASE VERIFICATION: INCOMPLETE")
        if mart_count == 0:
            _p("  accident_analytics_mart is empty — run the pipeline first:")
            _p("    python scripts/run_pipeline.py")
        else:
            _p("  Some tables are missing — check the errors above.")
    _p(sep)

    conn.close()
    return {"all_ok": all_tables_ok, "mart_count": mart_count, "lines": report_lines}


def main():
    parser = argparse.ArgumentParser(description="Verify the Traffic Accident Analytics database.")
    parser.add_argument("--verbose", action="store_true",
                        help="Show index list and additional details")
    parser.add_argument("--output", default=None,
                        help="Write report to this file (e.g. report.txt)")
    args = parser.parse_args()

    result = run_verification(verbose=args.verbose)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text("\n".join(result["lines"]), encoding="utf-8")
        print(f"\nReport saved to: {out_path.resolve()}")

    sys.exit(0 if result["all_ok"] else 1)


if __name__ == "__main__":
    main()
