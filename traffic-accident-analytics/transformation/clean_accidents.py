"""
transformation/clean_accidents.py
-----------------------------------
RAW → STAGING → CLEANED for the accident (collision) dataset.

STAGING step
------------
- Normalise all column names to snake_case
- Parse date (DD/MM/YYYY in STATS19) → datetime.date
- Parse time (HH:MM in STATS19) → datetime.time
- Standardise missing-value tokens (-1, "Data missing or out of range",
  "Unknown") → pd.NA / None
- Cast numeric columns to appropriate dtypes

CLEANED step
------------
- Detect and remove exact duplicates on accident_index
- Reject records with NULL accident_index
- Reject records with invalid latitude / longitude
- Reject records with unparseable date
- Reject records with invalid severity code (must be 1, 2 or 3)
- For non-critical NULLs (e.g. junction_detail) → leave as NULL
- Standardise severity to human-readable label
- Derive accident_hour from time
- Write cleaned CSV to data/cleaned/
- Write rejected records (with reason) to data/rejected/
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime

from config.config import (
    STAGING_DIR,
    CLEANED_DIR,
    REJECTED_DIR,
    SEVERITY_MAP,
    VALID_SEVERITIES,
    LAT_MIN, LAT_MAX,
    LON_MIN, LON_MAX,
    get_logger,
)

logger = get_logger(__name__)

# ── STATS19 tokens that mean "no data" ────────────────────────────────────────
_MISSING_TOKENS = {-1, "-1", "Data missing or out of range", "Unknown",
                   "Not known", "Data missing", ""}

# Columns that STATS19 uses -1 as a coded "unknown/missing" integer
_CODED_MISSING_INT_COLS = [
    "police_force", "accident_severity", "collision_severity",
    "number_of_vehicles", "number_of_casualties", "day_of_week",
    "local_authority_district", "local_authority_highway",
    "first_road_class", "road_type", "speed_limit",
    "junction_detail", "junction_control", "second_road_class",
    "pedestrian_crossing_human_control",
    "pedestrian_crossing_physical_facilities",
    "pedestrian_crossing",
    "light_conditions", "weather_conditions", "road_surface_conditions",
    "special_conditions_at_site", "carriageway_hazards",
    "urban_or_rural_area", "did_police_officer_attend_scene_of_accident",
    "trunk_road_flag",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _normalise_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Convert all column names to lowercase snake_case."""
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(r"[\s\-/]+", "_", regex=True)
        .str.replace(r"[^\w]", "", regex=True)
    )
    return df


def _replace_coded_missing(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace STATS19 -1 codes in known integer columns with pd.NA.
    The raw data uses -1 to indicate 'data missing or out of range'.
    """
    for col in _CODED_MISSING_INT_COLS:
        if col in df.columns:
            df[col] = df[col].replace(-1, pd.NA)
    return df


def _parse_date(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse the 'date' column from STATS19 format DD/MM/YYYY.
    Unparseable values become pd.NaT (handled in rejection step).
    """
    if "date" in df.columns:
        df["accident_date"] = pd.to_datetime(
            df["date"], format="%d/%m/%Y", errors="coerce"
        )
        df.drop(columns=["date"], inplace=True)
    return df


def _parse_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse 'time' column (HH:MM) into accident_time (string HH:MM kept)
    and derive accident_hour (int 0-23).
    """
    if "time" in df.columns:
        # Keep time as string for display; extract hour as integer
        df["accident_time"] = df["time"].astype(str).str.strip()
        df["accident_hour"] = pd.to_numeric(
            df["time"].astype(str).str.split(":").str[0],
            errors="coerce"
        ).astype("Int64")
        df.drop(columns=["time"], inplace=True)
    return df


def _cast_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Cast key numeric columns to nullable integer or float types."""
    int_cols = [
        "accident_severity", "number_of_vehicles", "number_of_casualties",
        "speed_limit", "road_type", "junction_detail", "light_conditions",
        "weather_conditions", "road_surface_conditions", "urban_or_rural_area",
        "day_of_week",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    float_cols = ["latitude", "longitude",
                  "location_easting_osgr", "location_northing_osgr"]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# ── Staging ────────────────────────────────────────────────────────────────────

def stage_accidents(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Apply STAGING transformations to raw accident data.

    Returns a cleaned-up but not yet quality-validated DataFrame.
    Writes a staging CSV to data/staging/.
    """
    logger.info("STAGING: starting accident staging (%d rows)", len(df_raw))
    df = df_raw.copy()

    df = _normalise_column_names(df)
    df = _replace_coded_missing(df)
    df = _parse_date(df)
    df = _parse_time(df)
    df = _cast_numeric(df)

    # Normalise accident_index: strip whitespace
    # The 2023 STATS19 release uses 'collision_index' — rename to 'accident_index'
    # for consistency with the rest of the pipeline.
    if "collision_index" in df.columns and "accident_index" not in df.columns:
        df.rename(columns={"collision_index": "accident_index"}, inplace=True)
    if "accident_index" in df.columns:
        df["accident_index"] = df["accident_index"].astype(str).str.strip()

    # Similarly rename collision_severity → accident_severity if needed
    if "collision_severity" in df.columns and "accident_severity" not in df.columns:
        df.rename(columns={"collision_severity": "accident_severity"}, inplace=True)

    # Rename collision_year → accident_year if present
    if "collision_year" in df.columns and "accident_year" not in df.columns:
        df.rename(columns={"collision_year": "accident_year"}, inplace=True)

    # Add staging timestamp
    df["_staged_at"] = datetime.utcnow().isoformat()

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    out_path = STAGING_DIR / "accidents_staged.csv"
    df.to_csv(out_path, index=False)
    logger.info("STAGING: accidents staged → %s (%d rows)", out_path, len(df))
    return df


# ── Cleaning ───────────────────────────────────────────────────────────────────

def clean_accidents(df_staged: pd.DataFrame) -> tuple:
    """
    Apply CLEANING and data-quality rejection to staged accident data.

    Returns
    -------
    (df_clean, df_rejected) : tuple of pd.DataFrame
        df_clean   – records that passed all checks
        df_rejected – records with at least one rejection reason
    """
    logger.info("CLEANING: starting accident cleaning (%d rows)", len(df_staged))
    df = df_staged.copy()

    rejected_rows = []   # list of dicts: original row + rejection_reason

    def _reject(mask: pd.Series, reason: str):
        """Mark rows matching *mask* as rejected, then drop them from df."""
        nonlocal df
        bad = df[mask].copy()
        bad["rejection_reason"] = reason
        rejected_rows.append(bad)
        df = df[~mask].copy()
        logger.info("  Rejected %d rows: %s", len(bad), reason)

    # ── 1. Missing accident_index ─────────────────────────────────────────────
    _reject(
        df["accident_index"].isna() | (df["accident_index"] == "nan"),
        "missing_accident_index",
    )

    # ── 2. Duplicate accident_index (keep first occurrence) ──────────────────
    dup_mask = df.duplicated(subset=["accident_index"], keep="first")
    _reject(dup_mask, "duplicate_accident_index")

    # ── 3. Invalid latitude ───────────────────────────────────────────────────
    if "latitude" in df.columns:
        lat_invalid = (
            df["latitude"].isna()
            | (df["latitude"] < LAT_MIN)
            | (df["latitude"] > LAT_MAX)
        )
        _reject(lat_invalid, "invalid_latitude")

    # ── 4. Invalid longitude ──────────────────────────────────────────────────
    if "longitude" in df.columns:
        lon_invalid = (
            df["longitude"].isna()
            | (df["longitude"] < LON_MIN)
            | (df["longitude"] > LON_MAX)
        )
        _reject(lon_invalid, "invalid_longitude")

    # ── 5. Invalid / missing date ─────────────────────────────────────────────
    if "accident_date" in df.columns:
        _reject(df["accident_date"].isna(), "invalid_or_missing_date")

    # ── 6. Invalid severity ───────────────────────────────────────────────────
    if "accident_severity" in df.columns:
        sev_invalid = ~df["accident_severity"].isin(VALID_SEVERITIES)
        # NaT severity counts as invalid
        sev_invalid = sev_invalid | df["accident_severity"].isna()
        _reject(sev_invalid, "invalid_severity")

    # ── 7. Invalid number_of_vehicles ────────────────────────────────────────
    if "number_of_vehicles" in df.columns:
        _reject(
            df["number_of_vehicles"].notna() & (df["number_of_vehicles"] < 0),
            "negative_vehicle_count",
        )

    # ── 8. Invalid number_of_casualties ──────────────────────────────────────
    if "number_of_casualties" in df.columns:
        _reject(
            df["number_of_casualties"].notna() & (df["number_of_casualties"] < 0),
            "negative_casualty_count",
        )

    # ── Post-cleaning derivations ─────────────────────────────────────────────

    # Map severity code → human-readable label
    if "accident_severity" in df.columns:
        df["severity_label"] = df["accident_severity"].map(SEVERITY_MAP)

    # Derive year, month, day_of_week_name from accident_date
    if "accident_date" in df.columns:
        df["accident_year"]  = df["accident_date"].dt.year
        df["accident_month"] = df["accident_date"].dt.month
        df["accident_day"]   = df["accident_date"].dt.day
        df["weekday_num"]    = df["accident_date"].dt.dayofweek   # 0=Mon
        df["weekday_name"]   = df["accident_date"].dt.day_name()

    # Mark as cleaned
    df["_cleaned_at"] = datetime.utcnow().isoformat()

    # ── Save cleaned data ─────────────────────────────────────────────────────
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    clean_path = CLEANED_DIR / "accidents_cleaned.csv"
    df.to_csv(clean_path, index=False)
    logger.info("CLEANING: cleaned accidents saved → %s (%d rows)", clean_path, len(df))

    # ── Save rejected data ────────────────────────────────────────────────────
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    if rejected_rows:
        df_rejected = pd.concat(rejected_rows, ignore_index=True)
        df_rejected["source"] = "accidents"
        df_rejected["rejected_at"] = datetime.utcnow().isoformat()
        rej_path = REJECTED_DIR / "accidents_rejected.csv"
        df_rejected.to_csv(rej_path, index=False)
        logger.info(
            "CLEANING: %d rejected accident records saved → %s",
            len(df_rejected), rej_path,
        )
    else:
        df_rejected = pd.DataFrame()
        logger.info("CLEANING: no records rejected from accident data.")

    return df, df_rejected


# ── Convenience wrapper ────────────────────────────────────────────────────────

def run_accident_pipeline(df_raw: pd.DataFrame) -> tuple:
    """Stage then clean accident data in one call."""
    df_staged  = stage_accidents(df_raw)
    df_clean, df_rejected = clean_accidents(df_staged)
    return df_clean, df_rejected


if __name__ == "__main__":
    from ingestion.accident_ingestion import ingest_accidents
    raw = ingest_accidents()
    clean, rejected = run_accident_pipeline(raw)
    print(f"\nClean: {len(clean):,} rows  |  Rejected: {len(rejected):,} rows")
    print(clean[["accident_index", "accident_date", "accident_severity",
                  "severity_label", "latitude", "longitude"]].head())
