"""
transformation/clean_casualties.py
------------------------------------
RAW → STAGING → CLEANED for the STATS19 casualty dataset.

Key columns:
    accident_index, vehicle_reference, casualty_reference,
    casualty_class, sex_of_casualty, age_of_casualty,
    casualty_severity, casualty_type
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime

from config.config import (
    STAGING_DIR, CLEANED_DIR, REJECTED_DIR,
    VALID_SEVERITIES, get_logger,
)

logger = get_logger(__name__)

_CODED_MISSING_INT_COLS = [
    "casualty_class", "sex_of_casualty", "age_band_of_casualty",
    "casualty_severity", "pedestrian_location", "pedestrian_movement",
    "car_passenger", "bus_or_coach_passenger",
    "pedestrian_road_maintenance_worker", "casualty_type",
    "casualty_home_area_type", "casualty_imd_decile",
    "enhanced_casualty_severity",
]


def _normalise_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = (
        df.columns.str.strip().str.lower()
        .str.replace(r"[\s\-/]+", "_", regex=True)
        .str.replace(r"[^\w]", "", regex=True)
    )
    return df


def _replace_coded_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Replace STATS19 -1 (unknown/missing) with NA."""
    for col in _CODED_MISSING_INT_COLS:
        if col in df.columns:
            df[col] = df[col].replace(-1, pd.NA)
    # age_of_casualty uses -1 for unknown
    if "age_of_casualty" in df.columns:
        df["age_of_casualty"] = pd.to_numeric(df["age_of_casualty"], errors="coerce")
        df["age_of_casualty"] = df["age_of_casualty"].where(
            df["age_of_casualty"] >= 0, other=np.nan
        )
    return df


def _cast_numeric(df: pd.DataFrame) -> pd.DataFrame:
    int_cols = [
        "casualty_class", "sex_of_casualty", "casualty_severity", "casualty_type",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    if "age_of_casualty" in df.columns:
        df["age_of_casualty"] = pd.to_numeric(
            df["age_of_casualty"], errors="coerce"
        )
    return df


def stage_casualties(df_raw: pd.DataFrame) -> pd.DataFrame:
    logger.info("STAGING: casualties (%d rows)", len(df_raw))
    df = df_raw.copy()
    df = _normalise_column_names(df)

    # 2023 STATS19 renamed accident_index → collision_index
    if "collision_index" in df.columns and "accident_index" not in df.columns:
        df.rename(columns={"collision_index": "accident_index"}, inplace=True)
    if "collision_year" in df.columns and "accident_year" not in df.columns:
        df.rename(columns={"collision_year": "accident_year"}, inplace=True)

    df = _replace_coded_missing(df)
    df = _cast_numeric(df)

    if "accident_index" in df.columns:
        df["accident_index"] = df["accident_index"].astype(str).str.strip()

    df["_staged_at"] = datetime.utcnow().isoformat()
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(STAGING_DIR / "casualties_staged.csv", index=False)
    logger.info("STAGING: casualties staged (%d rows)", len(df))
    return df


def clean_casualties(df_staged: pd.DataFrame) -> tuple:
    logger.info("CLEANING: casualties (%d rows)", len(df_staged))
    df = df_staged.copy()
    rejected_rows = []

    def _reject(mask, reason):
        nonlocal df
        bad = df[mask].copy()
        bad["rejection_reason"] = reason
        rejected_rows.append(bad)
        df = df[~mask].copy()
        logger.info("  Rejected %d casualty rows: %s", len(bad), reason)

    # Missing accident_index
    _reject(
        df["accident_index"].isna() | (df["accident_index"] == "nan"),
        "missing_accident_index",
    )

    # Duplicate (accident_index, vehicle_reference, casualty_reference)
    dup_cols = [c for c in
                ["accident_index", "vehicle_reference", "casualty_reference"]
                if c in df.columns]
    if dup_cols:
        _reject(df.duplicated(subset=dup_cols, keep="first"), "duplicate_casualty_record")

    # Invalid casualty_severity (must be 1, 2 or 3 when present)
    if "casualty_severity" in df.columns:
        bad_sev = (
            df["casualty_severity"].notna()
            & ~df["casualty_severity"].isin(VALID_SEVERITIES)
        )
        _reject(bad_sev, "invalid_casualty_severity")

    # Negative age
    if "age_of_casualty" in df.columns:
        _reject(
            df["age_of_casualty"].notna() & (df["age_of_casualty"] < 0),
            "negative_casualty_age",
        )

    df["_cleaned_at"] = datetime.utcnow().isoformat()
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(CLEANED_DIR / "casualties_cleaned.csv", index=False)
    logger.info("CLEANING: casualties saved (%d rows)", len(df))

    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    if rejected_rows:
        df_rejected = pd.concat(rejected_rows, ignore_index=True)
        df_rejected["source"] = "casualties"
        df_rejected["rejected_at"] = datetime.utcnow().isoformat()
        df_rejected.to_csv(REJECTED_DIR / "casualties_rejected.csv", index=False)
        logger.info("  Rejected casualties saved (%d rows)", len(df_rejected))
    else:
        df_rejected = pd.DataFrame()

    return df, df_rejected


def run_casualty_pipeline(df_raw: pd.DataFrame) -> tuple:
    return clean_casualties(stage_casualties(df_raw))
