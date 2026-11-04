"""
transformation/clean_vehicles.py
----------------------------------
RAW → STAGING → CLEANED for the STATS19 vehicle dataset.

NOTE on 2023 STATS19 column rename
------------------------------------
The 2023 release renamed accident_index → collision_index.
This module handles both names transparently.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime

from config.config import STAGING_DIR, CLEANED_DIR, REJECTED_DIR, get_logger

logger = get_logger(__name__)

_CODED_MISSING_INT_COLS = [
    "vehicle_type", "towing_and_articulation", "vehicle_manoeuvre",
    "vehicle_manoeuvre_historic",
    "vehicle_direction_from", "vehicle_direction_to",
    "vehicle_location_restricted_lane",
    "vehicle_location_restricted_lane_historic",
    "junction_location", "skidding_and_overturning",
    "hit_object_in_carriageway", "vehicle_leaving_carriageway",
    "hit_object_off_carriageway", "first_point_of_impact",
    "vehicle_left_hand_drive", "journey_purpose_of_driver",
    "journey_purpose_of_driver_historic",
    "sex_of_driver", "age_band_of_driver", "propulsion_code",
    "driver_imd_decile",
]


def _normalise_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = (
        df.columns.str.strip().str.lower()
        .str.replace(r"[\s\-/]+", "_", regex=True)
        .str.replace(r"[^\w]", "", regex=True)
    )
    return df


def _rename_2023_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    The 2023 STATS19 release renamed accident_index → collision_index.
    Normalise back to accident_index for pipeline consistency.
    """
    if "collision_index" in df.columns and "accident_index" not in df.columns:
        df.rename(columns={"collision_index": "accident_index"}, inplace=True)
    if "collision_year" in df.columns and "accident_year" not in df.columns:
        df.rename(columns={"collision_year": "accident_year"}, inplace=True)
    return df


def _replace_coded_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Replace STATS19 -1 (unknown/missing) with NA in all known columns."""
    for col in _CODED_MISSING_INT_COLS:
        if col in df.columns:
            df[col] = df[col].replace(-1, pd.NA)
    # age_of_driver and age_of_vehicle use -1 as unknown — replace before cast
    for col in ["age_of_driver", "age_of_vehicle", "engine_capacity_cc",
                "driver_imd_decile"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].where(df[col] >= 0, other=np.nan)
    return df


def _cast_numeric(df: pd.DataFrame) -> pd.DataFrame:
    int_cols = [
        "vehicle_type", "vehicle_manoeuvre", "sex_of_driver",
        "journey_purpose_of_driver", "propulsion_code",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    float_cols = ["engine_capacity_cc", "age_of_vehicle", "age_of_driver"]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def stage_vehicles(df_raw: pd.DataFrame) -> pd.DataFrame:
    logger.info("STAGING: vehicles (%d rows)", len(df_raw))
    df = df_raw.copy()
    df = _normalise_column_names(df)
    df = _rename_2023_columns(df)
    df = _replace_coded_missing(df)
    df = _cast_numeric(df)

    if "accident_index" in df.columns:
        df["accident_index"] = df["accident_index"].astype(str).str.strip()

    df["_staged_at"] = datetime.utcnow().isoformat()
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    out_path = STAGING_DIR / "vehicles_staged.csv"
    df.to_csv(out_path, index=False)
    logger.info("STAGING: vehicles staged → %s (%d rows)", out_path, len(df))
    return df


def clean_vehicles(df_staged: pd.DataFrame) -> tuple:
    logger.info("CLEANING: vehicles (%d rows)", len(df_staged))
    df = df_staged.copy()
    rejected_rows = []

    def _reject(mask, reason):
        nonlocal df
        bad = df[mask].copy()
        bad["rejection_reason"] = reason
        rejected_rows.append(bad)
        df = df[~mask].copy()
        logger.info("  Rejected %d vehicle rows: %s", len(bad), reason)

    # Missing accident_index
    _reject(
        df["accident_index"].isna() | (df["accident_index"] == "nan"),
        "missing_accident_index",
    )

    # Duplicate (accident_index, vehicle_reference)
    if "vehicle_reference" in df.columns:
        dup_mask = df.duplicated(
            subset=["accident_index", "vehicle_reference"], keep="first"
        )
        _reject(dup_mask, "duplicate_vehicle_record")

    # Impossible age_of_driver: reject truly negative values
    # Note: -1 should already be replaced with NA in staging.
    # This catches any edge cases that slip through.
    if "age_of_driver" in df.columns:
        _reject(
            df["age_of_driver"].notna() & (df["age_of_driver"] < 0),
            "negative_driver_age",
        )

    df["_cleaned_at"] = datetime.utcnow().isoformat()
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(CLEANED_DIR / "vehicles_cleaned.csv", index=False)
    logger.info("CLEANING: vehicles saved (%d rows)", len(df))

    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    if rejected_rows:
        df_rejected = pd.concat(rejected_rows, ignore_index=True)
        df_rejected["source"] = "vehicles"
        df_rejected["rejected_at"] = datetime.utcnow().isoformat()
        df_rejected.to_csv(REJECTED_DIR / "vehicles_rejected.csv", index=False)
        logger.info("  Rejected vehicles saved (%d rows)", len(df_rejected))
    else:
        df_rejected = pd.DataFrame()

    return df, df_rejected


def run_vehicle_pipeline(df_raw: pd.DataFrame) -> tuple:
    return clean_vehicles(stage_vehicles(df_raw))
