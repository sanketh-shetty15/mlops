"""
transformation/clean_weather.py
---------------------------------
Loads all cached weather Parquet files from data/raw/weather/,
performs light cleaning, and saves a single consolidated staging CSV
to data/staging/weather_staged.csv.

Open-Meteo data is generally clean, but we still:
- Verify expected columns are present
- Coerce numeric types
- Drop rows with null datetime
- Add weather_description if missing
- Deduplicate on (datetime, grid_lat, grid_lon)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from datetime import datetime

from config.config import (
    STAGING_DIR, CLEANED_DIR,
    WMO_WEATHER_DESCRIPTIONS,
    OPEN_METEO_HOURLY_VARS,
    get_logger,
)
from ingestion.weather_ingestion import load_all_weather

logger = get_logger(__name__)

_EXPECTED_COLS = ["datetime", "grid_lat", "grid_lon"] + OPEN_METEO_HOURLY_VARS


def clean_weather(df_raw: pd.DataFrame = None) -> pd.DataFrame:
    """
    Clean and stage weather data.

    Parameters
    ----------
    df_raw : pd.DataFrame, optional
        If None, loads from cached Parquet files via load_all_weather().

    Returns
    -------
    pd.DataFrame
        Cleaned weather DataFrame, also written to data/staging/ and
        data/cleaned/.
    """
    if df_raw is None:
        df_raw = load_all_weather()

    if df_raw.empty:
        logger.warning("No weather data to clean. Returning empty DataFrame.")
        return pd.DataFrame()

    logger.info("CLEANING: weather data (%d rows)", len(df_raw))
    df = df_raw.copy()

    # Ensure datetime column is actually datetime type
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        null_dt = df["datetime"].isna().sum()
        if null_dt:
            logger.warning("Dropping %d weather rows with null datetime", null_dt)
            df.dropna(subset=["datetime"], inplace=True)

    # Add weather description if not already present
    if "weather_code" in df.columns and "weather_description" not in df.columns:
        df["weather_description"] = (
            df["weather_code"].map(WMO_WEATHER_DESCRIPTIONS).fillna("Unknown")
        )

    # Coerce numeric weather columns
    numeric_cols = [
        "temperature_2m", "precipitation", "rain", "snowfall",
        "wind_speed_10m", "wind_direction_10m",
        "relative_humidity_2m", "visibility", "cloud_cover",
        "weather_code",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Deduplicate on (datetime, grid_lat, grid_lon)
    key_cols = [c for c in ["datetime", "grid_lat", "grid_lon"] if c in df.columns]
    before = len(df)
    df.drop_duplicates(subset=key_cols, keep="first", inplace=True)
    removed = before - len(df)
    if removed:
        logger.info("  Removed %d duplicate weather rows", removed)

    # Add helper columns for joining
    df["weather_date"] = df["datetime"].dt.date
    df["weather_hour"] = df["datetime"].dt.hour

    df["_cleaned_at"] = datetime.utcnow().isoformat()

    # Save to staging and cleaned
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)

    staging_path = STAGING_DIR / "weather_staged.csv"
    cleaned_path = CLEANED_DIR / "weather_cleaned.csv"

    df.to_csv(staging_path, index=False)
    df.to_csv(cleaned_path, index=False)

    logger.info(
        "CLEANING: weather cleaned → %s (%d rows, %d grid cells)",
        cleaned_path, len(df),
        df[["grid_lat", "grid_lon"]].drop_duplicates().shape[0] if "grid_lat" in df.columns else "?",
    )
    return df


if __name__ == "__main__":
    df = clean_weather()
    print(f"\nCleaned weather: {len(df):,} rows")
    if not df.empty:
        print(df.head(3).to_string())
