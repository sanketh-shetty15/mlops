"""
monitoring/data_drift.py
-------------------------
Detects input feature drift using the Kolmogorov-Smirnov (KS) test.

What is data drift?
--------------------
Data drift means the statistical distribution of input features has
changed compared to what the model was trained on. For example:
  - Accidents in new months have different hour distributions
  - Road conditions change seasonally
  - Weather patterns shift

Why does it matter?
-------------------
If the input data drifts significantly, the model's predictions may
become unreliable — it was trained on one distribution and is now
seeing a different one.

KS-test
-------
The Kolmogorov-Smirnov test compares two distributions by measuring
the maximum difference between their empirical CDFs.
  - p-value < 0.05 → distributions are significantly different → drift
  - p-value >= 0.05 → no significant drift detected

Usage
-----
    python monitoring/data_drift.py
    python monitoring/data_drift.py --recent-csv path/to/recent.csv
"""

import sys
import json
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    CLEANED_DIR,
    MODELS_DIR,
    ML_FEATURE_COLUMNS,
    RETRAIN_DRIFT_PVALUE_THRESHOLD,
    TRAIN_END_MONTH,
    get_logger,
)

logger = get_logger(__name__)

DRIFT_REPORT_PATH = MODELS_DIR / "drift_report.json"


def load_training_reference() -> pd.DataFrame:
    """
    Load the training subset of the cleaned data as the reference
    distribution. Training data = Jan–Aug 2023.
    """
    path = CLEANED_DIR / "accidents_with_weather.csv"
    if not path.exists():
        path = CLEANED_DIR / "accidents_cleaned.csv"

    df = pd.read_csv(path, low_memory=False)
    df["accident_date"] = pd.to_datetime(df["accident_date"], errors="coerce")
    df_train = df[df["accident_date"].dt.month <= TRAIN_END_MONTH].copy()
    logger.info(
        "Training reference loaded: %d rows (Jan–Aug 2023)", len(df_train)
    )
    return df_train


def load_recent_data(recent_csv: str = None) -> pd.DataFrame:
    """
    Load recent (post-training) data for drift comparison.
    Defaults to the test split (Nov–Dec 2023).
    """
    if recent_csv and Path(recent_csv).exists():
        df = pd.read_csv(recent_csv, low_memory=False)
        logger.info("Recent data loaded from %s (%d rows)", recent_csv, len(df))
        return df

    # Default: use Nov-Dec 2023 (test split) as "recent" data
    path = CLEANED_DIR / "accidents_with_weather.csv"
    if not path.exists():
        path = CLEANED_DIR / "accidents_cleaned.csv"

    df = pd.read_csv(path, low_memory=False)
    df["accident_date"] = pd.to_datetime(df["accident_date"], errors="coerce")
    df_recent = df[df["accident_date"].dt.month > 10].copy()   # Nov-Dec
    logger.info(
        "Recent data (test split): %d rows (Nov–Dec 2023)", len(df_recent)
    )
    return df_recent


def run_feature_drift(
    df_train: pd.DataFrame,
    df_recent: pd.DataFrame,
    p_threshold: float = RETRAIN_DRIFT_PVALUE_THRESHOLD,
) -> dict:
    """
    Run KS-test for every feature column.

    Returns
    -------
    dict with:
        feature_results : per-feature KS statistic and p-value
        drifted_features: list of features with p < threshold
        overall_drift   : True if any feature drifted
        retrain_required: True if drift is detected
    """
    feature_results = {}
    drifted_features = []

    for col in ML_FEATURE_COLUMNS:
        # Get non-null values from both sets
        train_vals  = df_train[col].dropna().values  if col in df_train.columns  else np.array([])
        recent_vals = df_recent[col].dropna().values if col in df_recent.columns else np.array([])

        if len(train_vals) < 30 or len(recent_vals) < 30:
            logger.debug("Skipping %s — insufficient data", col)
            feature_results[col] = {
                "ks_statistic": None,
                "p_value":      None,
                "drifted":      False,
                "note":         "insufficient data",
            }
            continue

        ks_stat, p_value = ks_2samp(train_vals, recent_vals)
        drifted = bool(p_value < p_threshold)

        feature_results[col] = {
            "ks_statistic": round(float(ks_stat), 4),
            "p_value":      round(float(p_value), 6),
            "drifted":      drifted,
        }

        if drifted:
            drifted_features.append(col)
            logger.warning(
                "DRIFT detected: %-30s  KS=%.4f  p=%.6f",
                col, ks_stat, p_value
            )
        else:
            logger.info(
                "No drift  : %-30s  KS=%.4f  p=%.6f",
                col, ks_stat, p_value
            )

    overall_drift    = len(drifted_features) > 0
    retrain_required = overall_drift

    summary = {
        "run_timestamp":   datetime.utcnow().isoformat(),
        "train_rows":      len(df_train),
        "recent_rows":     len(df_recent),
        "features_checked":len(ML_FEATURE_COLUMNS),
        "features_drifted":len(drifted_features),
        "drifted_features":drifted_features,
        "overall_drift":   overall_drift,
        "retrain_required":retrain_required,
        "p_threshold":     p_threshold,
        "feature_results": feature_results,
    }

    _save_report(summary, "drift_report.json")

    if retrain_required:
        logger.warning(
            "DATA DRIFT DETECTED on %d features: %s — "
            "retraining may be required.",
            len(drifted_features), drifted_features
        )
    else:
        logger.info("No significant data drift detected.")

    return summary


def _save_report(report: dict, filename: str) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = MODELS_DIR / filename
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("Drift report saved → %s", path)


def run_drift_check(recent_csv: str = None) -> dict:
    """Main entry point: load reference + recent data, run KS test."""
    df_train  = load_training_reference()
    df_recent = load_recent_data(recent_csv)
    return run_feature_drift(df_train, df_recent)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run feature drift detection")
    parser.add_argument("--recent-csv", default=None,
                        help="Path to recent data CSV (default: test split)")
    args = parser.parse_args()

    report = run_drift_check(args.recent_csv)
    print(f"\nDrift check complete.")
    print(f"  Features checked : {report['features_checked']}")
    print(f"  Features drifted : {report['features_drifted']}")
    print(f"  Drifted          : {report['drifted_features']}")
    print(f"  Retrain required : {report['retrain_required']}")
