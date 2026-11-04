"""
monitoring/performance_monitor.py
-----------------------------------
Monitors model performance on recent data and decides whether retraining
is needed.

Metrics tracked
---------------
macro_f1           — overall model quality (primary metric)
recall_fatal       — % of real Fatal accidents correctly identified
                     (most critical — missing Fatal is worst error)
fn_rate_fatal      — false-negative rate on Fatal class
                     = Fatal accidents predicted as Serious or Slight

Retraining criteria (any one triggers)
---------------------------------------
1. macro-F1 drops below RETRAIN_MACRO_F1_THRESHOLD (0.30)
2. Fatal false-negative rate exceeds RETRAIN_FN_RATE_THRESHOLD (0.50)
3. Data drift detected (from data_drift.py or location_drift.py)

Usage
-----
    python monitoring/performance_monitor.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import (
    f1_score, recall_score, confusion_matrix, classification_report
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    CLEANED_DIR,
    MODELS_DIR,
    BEST_MODEL_PATH,
    ML_FEATURE_COLUMNS,
    ML_TARGET_COLUMN,
    ML_CLASS_NAMES,
    RETRAIN_MACRO_F1_THRESHOLD,
    RETRAIN_FN_RATE_THRESHOLD,
    get_logger,
)

logger = get_logger(__name__)


def load_model():
    """Load the saved champion model."""
    if not BEST_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"No model found at {BEST_MODEL_PATH}. "
            "Run ml/train.py first."
        )
    return joblib.load(str(BEST_MODEL_PATH))


def get_model_type() -> str:
    """Read champion model type from training summary."""
    summary_path = MODELS_DIR / "training_summary.json"
    if summary_path.exists():
        with open(summary_path) as f:
            return json.load(f).get("champion_model", "rf")
    return "rf"


def evaluate_on_recent(
    pipeline,
    model_type: str,
    recent_months: list = None,
) -> dict:
    """
    Evaluate the current model on recent data (test split by default).

    Parameters
    ----------
    pipeline      : loaded sklearn pipeline
    model_type    : "rf" | "xgb" | "lgbm"
    recent_months : list of month numbers to use (default: [11, 12])

    Returns
    -------
    dict with performance metrics and retraining decision
    """
    if recent_months is None:
        recent_months = [11, 12]

    base_path = CLEANED_DIR / "accidents_with_weather.csv"
    if not base_path.exists():
        base_path = CLEANED_DIR / "accidents_cleaned.csv"

    df = pd.read_csv(base_path, low_memory=False)
    df["accident_date"] = pd.to_datetime(df["accident_date"], errors="coerce")

    df_recent = df[df["accident_date"].dt.month.isin(recent_months)].copy()
    df_recent.dropna(subset=[ML_TARGET_COLUMN], inplace=True)
    df_recent[ML_TARGET_COLUMN] = df_recent[ML_TARGET_COLUMN].astype(int)
    df_recent = df_recent[df_recent[ML_TARGET_COLUMN].isin([1, 2, 3])]

    if df_recent.empty:
        logger.warning("No recent data found for months %s", recent_months)
        return {"error": "no_recent_data", "retrain_required": False}

    logger.info(
        "Performance monitor: evaluating on %d recent records (months %s)",
        len(df_recent), recent_months
    )

    # Build feature matrix
    for col in ML_FEATURE_COLUMNS:
        if col not in df_recent.columns:
            df_recent[col] = np.nan
    X_recent = df_recent[ML_FEATURE_COLUMNS]
    y_recent = df_recent[ML_TARGET_COLUMN]

    # XGBoost uses 0-indexed labels
    if model_type == "xgb":
        y_eval = y_recent - 1
    else:
        y_eval = y_recent

    # Predict
    y_pred_raw = pipeline.predict(X_recent)
    if model_type == "xgb":
        y_pred = y_pred_raw  # already 0-indexed
    else:
        y_pred = y_pred_raw - 1  # remap to 0-indexed for metrics

    classes_present = sorted(np.unique(y_eval))

    # ── Core metrics ──────────────────────────────────────────────────────────
    macro_f1 = float(f1_score(y_eval, y_pred, average="macro", zero_division=0))

    recall_per_class = recall_score(
        y_eval, y_pred, labels=classes_present,
        average=None, zero_division=0
    )

    # 0=Fatal, 1=Serious, 2=Slight
    recall_fatal   = float(recall_per_class[0]) if len(recall_per_class) > 0 else 0.0
    recall_serious = float(recall_per_class[1]) if len(recall_per_class) > 1 else 0.0
    recall_slight  = float(recall_per_class[2]) if len(recall_per_class) > 2 else 0.0

    # ── Fatal false-negative rate ─────────────────────────────────────────────
    # FN rate = Fatal accidents that were NOT predicted as Fatal
    fatal_mask    = (y_eval == 0)
    total_fatal   = int(fatal_mask.sum())
    fn_fatal      = int((fatal_mask & (y_pred != 0)).sum())
    fn_rate_fatal = float(fn_fatal / max(total_fatal, 1))

    # ── Class distribution ────────────────────────────────────────────────────
    class_counts = y_recent.map(ML_CLASS_NAMES).value_counts().to_dict()

    # ── Retraining decision ───────────────────────────────────────────────────
    retrain_reasons = []

    if macro_f1 < RETRAIN_MACRO_F1_THRESHOLD:
        retrain_reasons.append(
            f"macro_f1={macro_f1:.4f} < threshold={RETRAIN_MACRO_F1_THRESHOLD}"
        )

    if fn_rate_fatal > RETRAIN_FN_RATE_THRESHOLD:
        retrain_reasons.append(
            f"fn_rate_fatal={fn_rate_fatal:.4f} > threshold={RETRAIN_FN_RATE_THRESHOLD}"
        )

    retrain_required = len(retrain_reasons) > 0

    # Check if drift was detected by other monitors
    drift_report = MODELS_DIR / "drift_report.json"
    if drift_report.exists():
        with open(drift_report) as f:
            drift = json.load(f)
        if drift.get("retrain_required", False):
            retrain_reasons.append("feature_drift_detected")
            retrain_required = True

    loc_report = MODELS_DIR / "location_drift_report.json"
    if loc_report.exists():
        with open(loc_report) as f:
            loc = json.load(f)
        if loc.get("retrain_required", False):
            retrain_reasons.append("location_drift_detected")
            retrain_required = True

    summary = {
        "run_timestamp":    datetime.utcnow().isoformat(),
        "recent_months":    recent_months,
        "recent_rows":      int(len(df_recent)),
        "class_counts":     class_counts,
        "macro_f1":         round(macro_f1, 4),
        "recall_fatal":     round(recall_fatal, 4),
        "recall_serious":   round(recall_serious, 4),
        "recall_slight":    round(recall_slight, 4),
        "total_fatal":      total_fatal,
        "fn_fatal":         fn_fatal,
        "fn_rate_fatal":    round(fn_rate_fatal, 4),
        "retrain_required": retrain_required,
        "retrain_reasons":  retrain_reasons,
        "thresholds": {
            "min_macro_f1":    RETRAIN_MACRO_F1_THRESHOLD,
            "max_fn_rate":     RETRAIN_FN_RATE_THRESHOLD,
        },
    }

    # Save report
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = MODELS_DIR / "performance_report.json"
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Performance report saved → %s", report_path)

    # Log summary
    logger.info(
        "Performance: macro-F1=%.4f | recall_fatal=%.4f | fn_rate_fatal=%.4f",
        macro_f1, recall_fatal, fn_rate_fatal
    )

    if retrain_required:
        logger.warning(
            "RETRAINING REQUIRED: %s", " | ".join(retrain_reasons)
        )
    else:
        logger.info("Model performance is acceptable. No retraining needed.")

    return summary


def run_full_monitoring() -> dict:
    """Run all monitoring checks and return combined report."""
    logger.info("=" * 60)
    logger.info("  RUNNING FULL MONITORING SUITE")
    logger.info("=" * 60)

    pipeline   = load_model()
    model_type = get_model_type()

    perf = evaluate_on_recent(pipeline, model_type)

    # Import drift checks
    from monitoring.data_drift     import run_drift_check
    from monitoring.location_drift import run_location_drift

    drift    = run_drift_check()
    loc_drift = run_location_drift()

    retrain_required = (
        perf.get("retrain_required", False) or
        drift.get("retrain_required", False) or
        loc_drift.get("retrain_required", False)
    )

    combined = {
        "run_timestamp":    datetime.utcnow().isoformat(),
        "retrain_required": retrain_required,
        "performance":      perf,
        "feature_drift":    drift,
        "location_drift":   loc_drift,
    }

    combined_path = MODELS_DIR / "monitoring_combined.json"
    with open(combined_path, "w") as f:
        json.dump(combined, f, indent=2, default=str)
    logger.info("Combined monitoring report → %s", combined_path)

    logger.info("=" * 60)
    logger.info(
        "  MONITORING COMPLETE | retrain_required=%s", retrain_required
    )
    logger.info("=" * 60)

    return combined


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    report = run_full_monitoring()
    print(f"\nMonitoring Summary:")
    p = report["performance"]
    print(f"  macro-F1      : {p.get('macro_f1', 'N/A')}")
    print(f"  recall_fatal  : {p.get('recall_fatal', 'N/A')}")
    print(f"  fn_rate_fatal : {p.get('fn_rate_fatal', 'N/A')}")
    print(f"  Retrain       : {report['retrain_required']}")
    if p.get("retrain_reasons"):
        print(f"  Reasons       : {p['retrain_reasons']}")
