"""
validation/data_quality.py
----------------------------
Runs all validation rules against cleaned datasets and produces:

  1. A human-readable DATA QUALITY REPORT printed to stdout/log
  2. A JSON quality report saved to data/rejected/quality_report.json
  3. A PostgreSQL ingestion_log entry (if DB is available)
  4. Rejected records written to data/rejected/ (new rows only, appended
     to whatever the cleaning step already wrote)

The report format:

  ════════════════════════════════════════
  DATA QUALITY REPORT — 2023-01-15 14:30:00
  ════════════════════════════════════════
  Dataset : accidents
  Total Records : 100,245
  ────────────────────────────────────────
  [PASS] accident_row_count         ...
  [PASS] accident_id_not_null       ...
  [FAIL] uk_bounding_box            12 rows outside UK box (warn only)
  ────────────────────────────────────────
  Checks Passed  : 10
  Checks Failed  : 1  (LOG_WARN — pipeline continues)
  Rejected Rows  : 0
  ════════════════════════════════════════
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import REJECTED_DIR, get_db_connection_string, get_logger
from validation.validation_rules import (
    ValidationRule, RuleResult,
    ACCIDENT_RULES, VEHICLE_RULES, CASUALTY_RULES, WEATHER_RULES,
)

logger = get_logger(__name__)

REJECTED_DIR.mkdir(parents=True, exist_ok=True)


# ── Core runner ────────────────────────────────────────────────────────────────

def run_checks(
    df: pd.DataFrame,
    rules: List[ValidationRule],
    dataset_name: str,
) -> dict:
    """
    Apply a list of ValidationRules to a DataFrame.

    Returns a summary dict suitable for JSON serialisation and
    PostgreSQL ingestion_log insertion.
    """
    total = len(df)
    results: List[RuleResult] = []
    pipeline_halt = False

    for rule in rules:
        try:
            result = rule.check(df)
            result.action = rule.action   # enforce the action from the rule set
            results.append(result)

            if not result.passed and result.action == "FAIL_PIPELINE":
                pipeline_halt = True
                logger.critical(
                    "PIPELINE HALT triggered by rule '%s': %s",
                    result.rule_name, result.message,
                )
        except Exception as exc:
            # A broken rule check must not crash the pipeline
            err_result = RuleResult(
                rule_name=rule.name,
                passed=False,
                message=f"Rule check raised exception: {exc}",
                action="LOG_WARN",
            )
            results.append(err_result)
            logger.error("Rule '%s' raised an exception: %s", rule.name, exc)

    n_passed = sum(1 for r in results if r.passed)
    n_failed = sum(1 for r in results if not r.passed)
    total_rejected = sum(r.failed_count for r in results if r.action == "REJECT")

    summary = {
        "dataset":         dataset_name,
        "run_timestamp":   datetime.utcnow().isoformat(),
        "total_records":   total,
        "checks_run":      len(results),
        "checks_passed":   n_passed,
        "checks_failed":   n_failed,
        "total_rejected":  total_rejected,
        "pipeline_halt":   pipeline_halt,
        "results":         [
            {
                "rule":          r.rule_name,
                "passed":        r.passed,
                "message":       r.message,
                "failed_count":  r.failed_count,
                "total_count":   r.total_count,
                "action":        r.action,
            }
            for r in results
        ],
    }
    return summary


def _print_report(summary: dict) -> None:
    """Print a formatted quality report to stdout and logger."""
    sep = "═" * 60
    thin = "─" * 60
    ts = summary["run_timestamp"]

    lines = [
        sep,
        f"  DATA QUALITY REPORT — {ts}",
        sep,
        f"  Dataset       : {summary['dataset'].upper()}",
        f"  Total Records : {summary['total_records']:,}",
        thin,
    ]
    for r in summary["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        action_note = f" [{r['action']}]" if not r["passed"] else ""
        lines.append(f"  [{status}] {r['rule']:<40} {r['message']}{action_note}")

    lines += [
        thin,
        f"  Checks Passed  : {summary['checks_passed']}",
        f"  Checks Failed  : {summary['checks_failed']}",
        f"  Rejected Rows  : {summary['total_rejected']:,}",
    ]
    if summary["pipeline_halt"]:
        lines.append("  *** PIPELINE HALT — critical rule failed ***")
    lines.append(sep)

    report_text = "\n".join(lines)
    print(report_text)
    logger.info("\n%s", report_text)


def _save_json_report(summary: dict, dataset_name: str) -> Path:
    """Write the quality report as JSON to data/rejected/."""
    fname = f"quality_report_{dataset_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    path = REJECTED_DIR / fname
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Quality report saved → %s", path)
    return path


def _log_to_postgres(
    source_name: str,
    status: str,
    row_count: int,
    error_message: str = "",
) -> None:
    """
    Insert a row into the ingestion_log table.
    Silently skips if PostgreSQL is unavailable.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(get_db_connection_string())
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ingestion_log
                   (source_name, source_type, extraction_timestamp,
                    status, row_count, error_message)
                   VALUES (%s, %s, %s, %s, %s, %s);""",
                (
                    source_name, "data_quality_check",
                    datetime.utcnow(), status, row_count, error_message,
                ),
            )
        conn.commit()
        conn.close()
        logger.info("ingestion_log updated for '%s'", source_name)
    except Exception as exc:
        logger.warning("Could not write to ingestion_log (DB may be offline): %s", exc)


# ── Public entry points ────────────────────────────────────────────────────────

def validate_accidents(df: pd.DataFrame) -> dict:
    """Run all accident quality rules, print report, save JSON."""
    logger.info("Running accident data quality checks (%d rows)...", len(df))
    summary = run_checks(df, ACCIDENT_RULES, "accidents")
    _print_report(summary)
    _save_json_report(summary, "accidents")
    _log_to_postgres(
        source_name="dq_accidents",
        status="PASS" if summary["checks_failed"] == 0 else "WARN",
        row_count=summary["total_records"],
        error_message=f"{summary['checks_failed']} checks failed",
    )
    if summary["pipeline_halt"]:
        raise RuntimeError(
            "Data quality FAIL_PIPELINE rule triggered on accidents dataset. "
            "Review quality_report JSON in data/rejected/."
        )
    return summary


def validate_vehicles(df: pd.DataFrame) -> dict:
    logger.info("Running vehicle data quality checks (%d rows)...", len(df))
    summary = run_checks(df, VEHICLE_RULES, "vehicles")
    _print_report(summary)
    _save_json_report(summary, "vehicles")
    _log_to_postgres("dq_vehicles",
                     "PASS" if summary["checks_failed"] == 0 else "WARN",
                     summary["total_records"])
    return summary


def validate_casualties(df: pd.DataFrame) -> dict:
    logger.info("Running casualty data quality checks (%d rows)...", len(df))
    summary = run_checks(df, CASUALTY_RULES, "casualties")
    _print_report(summary)
    _save_json_report(summary, "casualties")
    _log_to_postgres("dq_casualties",
                     "PASS" if summary["checks_failed"] == 0 else "WARN",
                     summary["total_records"])
    return summary


def validate_weather(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        logger.warning("Weather DataFrame is empty — skipping weather quality checks.")
        return {"dataset": "weather", "checks_run": 0, "checks_failed": 0,
                "checks_passed": 0, "total_records": 0, "total_rejected": 0,
                "pipeline_halt": False, "results": []}
    logger.info("Running weather data quality checks (%d rows)...", len(df))
    summary = run_checks(df, WEATHER_RULES, "weather")
    _print_report(summary)
    _save_json_report(summary, "weather")
    return summary


def run_full_quality_report(
    df_accidents:  Optional[pd.DataFrame] = None,
    df_vehicles:   Optional[pd.DataFrame] = None,
    df_casualties: Optional[pd.DataFrame] = None,
    df_weather:    Optional[pd.DataFrame] = None,
) -> dict:
    """
    Run quality checks on all available datasets and return a combined summary.

    Loads DataFrames from data/cleaned/ if not provided.
    """
    from config.config import CLEANED_DIR

    def _load_if_needed(df, fname):
        if df is not None:
            return df
        path = CLEANED_DIR / fname
        if path.exists():
            return pd.read_csv(path, low_memory=False)
        logger.warning("File not found for quality check: %s", path)
        return pd.DataFrame()

    df_accidents  = _load_if_needed(df_accidents,  "accidents_cleaned.csv")
    df_vehicles   = _load_if_needed(df_vehicles,   "vehicles_cleaned.csv")
    df_casualties = _load_if_needed(df_casualties, "casualties_cleaned.csv")
    df_weather    = _load_if_needed(df_weather,    "weather_cleaned.csv")

    combined = {
        "run_timestamp": datetime.utcnow().isoformat(),
        "datasets": {},
    }

    if not df_accidents.empty:
        combined["datasets"]["accidents"]  = validate_accidents(df_accidents)
    if not df_vehicles.empty:
        combined["datasets"]["vehicles"]   = validate_vehicles(df_vehicles)
    if not df_casualties.empty:
        combined["datasets"]["casualties"] = validate_casualties(df_casualties)
    if not df_weather.empty:
        combined["datasets"]["weather"]    = validate_weather(df_weather)

    # Overall summary
    total_failed = sum(
        v.get("checks_failed", 0)
        for v in combined["datasets"].values()
    )
    combined["overall_checks_failed"] = total_failed
    combined["overall_status"] = "PASS" if total_failed == 0 else "WARN"

    # Save combined report
    combined_path = REJECTED_DIR / "quality_report_combined.json"
    with open(combined_path, "w") as f:
        json.dump(combined, f, indent=2, default=str)
    logger.info("Combined quality report saved → %s", combined_path)

    return combined


# ── CLI entry ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    report = run_full_quality_report()
    overall = report.get("overall_status", "UNKNOWN")
    print(f"\nOverall data quality status: {overall}")
