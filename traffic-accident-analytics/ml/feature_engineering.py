"""
ml/feature_engineering.py
---------------------------
Builds the model-ready feature matrix from accidents_with_weather.csv.

Why chronological split (not random)?
--------------------------------------
Accident patterns change over time — seasonal effects, road changes,
weather patterns. A random split would let the model "peek" at future
data during training. Chronological split simulates real deployment:
train on the past, predict on unseen future months.

Split:
    Train      : January  – August 2023   (~67%)
    Validation : September – October 2023  (~17%)
    Test       : November – December 2023  (~16%)

Class imbalance:
    Fatal:   ~2%   ← most important to detect
    Serious: ~13%
    Slight:  ~85%  ← dominates

The target variable y is remapped to 0-indexed for sklearn:
    1 (Fatal)   → 0
    2 (Serious) → 1
    3 (Slight)  → 2

This is reversed before display so labels always show Fatal/Serious/Slight.
"""

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    CLEANED_DIR,
    MODELS_DIR,
    FEATURE_NAMES_PATH,
    ML_FEATURE_COLUMNS,
    ML_TARGET_COLUMN,
    ML_CLASS_NAMES,
    TRAIN_END_MONTH,
    VAL_END_MONTH,
    get_logger,
)

logger = get_logger(__name__)


# ── Public API ─────────────────────────────────────────────────────────────────

def load_raw_data() -> pd.DataFrame:
    """
    Load accidents_with_weather.csv — the output of Part 1 pipeline.
    Falls back to accidents_cleaned.csv if weather join is unavailable.
    """
    wx_path    = CLEANED_DIR / "accidents_with_weather.csv"
    clean_path = CLEANED_DIR / "accidents_cleaned.csv"

    if wx_path.exists():
        logger.info("Loading: %s", wx_path)
        df = pd.read_csv(wx_path, low_memory=False)
    elif clean_path.exists():
        logger.warning(
            "accidents_with_weather.csv not found — using accidents_cleaned.csv. "
            "Weather features will be missing (NULL)."
        )
        df = pd.read_csv(clean_path, low_memory=False)
    else:
        raise FileNotFoundError(
            f"No cleaned accident data found in {CLEANED_DIR}. "
            "Run the Part 1 pipeline first."
        )

    logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))
    return df


def build_feature_matrix(df: pd.DataFrame) -> tuple:
    """
    Select and clean the feature columns, extract the target column.

    Returns
    -------
    X : pd.DataFrame — feature matrix (104,246 rows × 15 cols)
    y : pd.Series    — target labels (1=Fatal, 2=Serious, 3=Slight)
    df_with_features : pd.DataFrame — original df with accident_date kept
    """
    # Ensure accident_date is datetime
    df = df.copy()
    df["accident_date"] = pd.to_datetime(df["accident_date"], errors="coerce")

    # Drop rows where target is missing
    before = len(df)
    df.dropna(subset=[ML_TARGET_COLUMN], inplace=True)
    dropped = before - len(df)
    if dropped:
        logger.warning("Dropped %d rows with null target column", dropped)

    # Ensure target is integer
    df[ML_TARGET_COLUMN] = df[ML_TARGET_COLUMN].astype(int)

    # Only keep valid severity values (1, 2, 3)
    valid_mask = df[ML_TARGET_COLUMN].isin([1, 2, 3])
    df = df[valid_mask].copy()
    logger.info("Records with valid severity: %d", len(df))

    # Select available feature columns (some may be absent if using
    # accidents_cleaned.csv without weather join)
    available_features = [c for c in ML_FEATURE_COLUMNS if c in df.columns]
    missing_features   = [c for c in ML_FEATURE_COLUMNS if c not in df.columns]

    if missing_features:
        logger.warning("Missing feature columns (will be added as NaN): %s",
                       missing_features)
        for col in missing_features:
            df[col] = np.nan

    X = df[ML_FEATURE_COLUMNS].copy()
    y = df[ML_TARGET_COLUMN].copy()

    logger.info(
        "Feature matrix: %d rows × %d columns | Target distribution:\n%s",
        len(X), len(X.columns),
        y.map(ML_CLASS_NAMES).value_counts().to_string()
    )

    # Save feature names for later use in API / monitoring
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(FEATURE_NAMES_PATH, "w") as f:
        json.dump(ML_FEATURE_COLUMNS, f, indent=2)
    logger.info("Feature names saved → %s", FEATURE_NAMES_PATH)

    return X, y, df


def chronological_split(X: pd.DataFrame, y: pd.Series,
                         df: pd.DataFrame) -> tuple:
    """
    Split data chronologically using accident_date.

    Returns
    -------
    X_train, X_val, X_test : pd.DataFrame
    y_train, y_val, y_test : pd.Series
    """
    accident_month = df["accident_date"].dt.month

    train_mask = accident_month <= TRAIN_END_MONTH
    val_mask   = (accident_month > TRAIN_END_MONTH) & \
                 (accident_month <= VAL_END_MONTH)
    test_mask  = accident_month > VAL_END_MONTH

    X_train = X[train_mask]
    X_val   = X[val_mask]
    X_test  = X[test_mask]
    y_train = y[train_mask]
    y_val   = y[val_mask]
    y_test  = y[test_mask]

    logger.info(
        "Chronological split:"
        "\n  Train : %d rows (Jan–Aug 2023)  — %.1f%%"
        "\n  Val   : %d rows (Sep–Oct 2023)  — %.1f%%"
        "\n  Test  : %d rows (Nov–Dec 2023)  — %.1f%%",
        len(X_train), 100 * len(X_train) / len(X),
        len(X_val),   100 * len(X_val)   / len(X),
        len(X_test),  100 * len(X_test)  / len(X),
    )

    # Log class distribution per split
    for name, y_split in [("Train", y_train), ("Val", y_val),
                            ("Test", y_test)]:
        dist = y_split.map(ML_CLASS_NAMES).value_counts()
        logger.info("%s class distribution:\n%s", name, dist.to_string())

    return X_train, X_val, X_test, y_train, y_val, y_test


def build_preprocessor() -> Pipeline:
    """
    Build a sklearn preprocessing pipeline:
    1. SimpleImputer  — fill NaN with median (robust to outliers)
    2. StandardScaler — zero mean, unit variance (helps tree models less
                         but is required for downstream linear baselines)

    Returns the unfitted Pipeline object.
    To fit: preprocessor.fit(X_train)
    To transform: X_transformed = preprocessor.transform(X)
    """
    preprocessor = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
    ])
    return preprocessor


def prepare_all() -> tuple:
    """
    Convenience function — loads data, builds features, splits, returns
    everything needed for training.

    Returns
    -------
    X_train, X_val, X_test : pd.DataFrame
    y_train, y_val, y_test : pd.Series
    preprocessor           : unfitted sklearn Pipeline
    """
    df                          = load_raw_data()
    X, y, df_full               = build_feature_matrix(df)
    X_train, X_val, X_test, \
    y_train, y_val, y_test      = chronological_split(X, y, df_full)
    preprocessor                = build_preprocessor()
    return X_train, X_val, X_test, y_train, y_val, y_test, preprocessor


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    X_train, X_val, X_test, y_train, y_val, y_test, prep = prepare_all()
    print(f"\nFeature engineering complete.")
    print(f"  Train : {len(X_train):,} rows")
    print(f"  Val   : {len(X_val):,} rows")
    print(f"  Test  : {len(X_test):,} rows")
    print(f"  Features: {list(X_train.columns)}")
