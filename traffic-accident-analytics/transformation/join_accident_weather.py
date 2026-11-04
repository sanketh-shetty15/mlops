"""
transformation/join_accident_weather.py
-----------------------------------------
Joins cleaned accident records with hourly weather data.

Matching strategy (documented)
--------------------------------
Each accident has a latitude, longitude, date and time.

Step 1 — Grid snap
    The accident's latitude and longitude are rounded to the nearest
    0.5-degree grid cell (matching the weather ingestion strategy).
    This links each accident to the weather data already fetched for
    that cell.

Step 2 — Nearest-hour matching
    Weather data is hourly. An accident reported at 08:37 is matched to
    the 09:00 observation (nearest integer hour, rounding 30-min up).
    Formally: weather_hour = round(accident_hour + accident_minute/60).

    Example:
        Accident time 08:37 → fractional hour 8.617 → rounds to 9 → matches 09:00
        Accident time 08:22 → fractional hour 8.367 → rounds to 8 → matches 08:00

Step 3 — Left join
    All valid accidents are retained, even when no weather data exists
    for a particular grid cell or hour. In that case weather columns
    will be NULL. This is by design — weather enrichment failure must not
    cause valid accident records to be lost.

Step 4 — Missing weather logging
    The number of accidents where weather data could not be matched is
    logged explicitly so the quality of enrichment can be monitored.

Output
------
data/cleaned/accidents_with_weather.csv
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime

from config.config import (
    CLEANED_DIR, STAGING_DIR,
    WEATHER_GRID_RESOLUTION,
    get_logger,
)
from ingestion.weather_ingestion import snap_to_grid, _nearest_hour

logger = get_logger(__name__)


def join_accident_weather(
    df_accidents: pd.DataFrame = None,
    df_weather: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Enrich accident records with nearest-hour weather observations.

    Parameters
    ----------
    df_accidents : pd.DataFrame, optional
        Cleaned accidents. If None, loads from data/cleaned/accidents_cleaned.csv.
    df_weather : pd.DataFrame, optional
        Cleaned weather. If None, loads from data/cleaned/weather_cleaned.csv.

    Returns
    -------
    pd.DataFrame
        Accident rows with weather columns appended. Rows without a
        weather match have NaN in weather columns.
    """
    # ── Load data if not provided ─────────────────────────────────────────────
    if df_accidents is None:
        acc_path = CLEANED_DIR / "accidents_cleaned.csv"
        if not acc_path.exists():
            raise FileNotFoundError(f"Cleaned accidents not found at {acc_path}")
        df_accidents = pd.read_csv(acc_path, low_memory=False)
        logger.info("Loaded cleaned accidents: %d rows", len(df_accidents))

    if df_weather is None:
        wx_path = CLEANED_DIR / "weather_cleaned.csv"
        if not wx_path.exists():
            logger.warning(
                "Cleaned weather not found at %s. "
                "All weather columns will be NULL.", wx_path
            )
            # Return accidents unchanged with null weather columns
            df_accidents["weather_matched"] = False
            return df_accidents
        df_weather = pd.read_csv(wx_path, low_memory=False)
        logger.info("Loaded cleaned weather: %d rows", len(df_weather))

    if df_weather.empty:
        logger.warning("Weather DataFrame is empty. Returning accidents with null weather.")
        df_accidents["weather_matched"] = False
        return df_accidents

    logger.info("Joining accidents (%d) with weather (%d rows)...",
                len(df_accidents), len(df_weather))

    df_acc = df_accidents.copy()

    # ── Step 1: Grid snap accident coordinates ────────────────────────────────
    def _snap_row(row):
        try:
            return snap_to_grid(float(row["latitude"]), float(row["longitude"]))
        except (TypeError, ValueError):
            return (None, None)

    snapped = df_acc.apply(_snap_row, axis=1)
    df_acc["join_grid_lat"] = snapped.apply(lambda t: t[0])
    df_acc["join_grid_lon"] = snapped.apply(lambda t: t[1])

    # ── Step 2: Nearest-hour for accident time ────────────────────────────────
    if "accident_time" in df_acc.columns:
        df_acc["join_hour"] = df_acc["accident_time"].apply(_nearest_hour)
    elif "accident_hour" in df_acc.columns:
        df_acc["join_hour"] = df_acc["accident_hour"]
    else:
        df_acc["join_hour"] = None

    # ── Step 3: Build join key on weather side ────────────────────────────────
    # Ensure weather has date and hour columns for joining
    if "datetime" in df_weather.columns:
        df_weather["datetime"] = pd.to_datetime(df_weather["datetime"], errors="coerce")
        df_weather["weather_date"] = df_weather["datetime"].dt.date
        df_weather["weather_hour"] = df_weather["datetime"].dt.hour

    # Ensure accident has date as a date object for matching
    if "accident_date" in df_acc.columns:
        df_acc["accident_date"] = pd.to_datetime(df_acc["accident_date"], errors="coerce")
        df_acc["join_date"] = df_acc["accident_date"].dt.date
    else:
        df_acc["join_date"] = None

    # Select only the weather columns we want to bring across
    weather_cols = [
        "weather_date", "weather_hour", "grid_lat", "grid_lon",
        "temperature_2m", "precipitation", "rain", "snowfall",
        "weather_code", "weather_description",
        "wind_speed_10m", "wind_direction_10m",
        "relative_humidity_2m", "visibility", "cloud_cover",
    ]
    weather_cols_present = [c for c in weather_cols if c in df_weather.columns]
    df_wx_slim = df_weather[weather_cols_present].copy()
    df_wx_slim.rename(
        columns={"grid_lat": "wx_grid_lat", "grid_lon": "wx_grid_lon"},
        inplace=True,
    )

    # Convert date columns to same type for merge
    df_wx_slim["weather_date"] = pd.to_datetime(df_wx_slim["weather_date"]).dt.date
    df_acc["join_date"] = pd.to_datetime(df_acc["join_date"], errors="coerce").dt.date

    # ── Step 4: Merge ─────────────────────────────────────────────────────────
    # Left join: accident → weather on (date, hour, snapped_lat, snapped_lon)
    df_merged = df_acc.merge(
        df_wx_slim,
        how="left",
        left_on=["join_date", "join_hour", "join_grid_lat", "join_grid_lon"],
        right_on=["weather_date", "weather_hour", "wx_grid_lat", "wx_grid_lon"],
    )

    # ── Step 5: Track match quality ───────────────────────────────────────────
    df_merged["weather_matched"] = df_merged["temperature_2m"].notna()
    matched = df_merged["weather_matched"].sum()
    total = len(df_merged)
    match_pct = 100 * matched / total if total else 0

    logger.info(
        "Weather join complete: %d/%d accidents matched (%.1f%%). "
        "%d unmatched accidents retain NULL weather columns.",
        matched, total, match_pct, total - matched,
    )

    # Drop internal join helper columns
    drop_cols = [
        "join_grid_lat", "join_grid_lon", "join_hour", "join_date",
        "wx_grid_lat", "wx_grid_lon", "weather_date", "weather_hour",
    ]
    df_merged.drop(columns=[c for c in drop_cols if c in df_merged.columns],
                   inplace=True)

    df_merged["_joined_at"] = datetime.utcnow().isoformat()

    # ── Save ──────────────────────────────────────────────────────────────────
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEANED_DIR / "accidents_with_weather.csv"
    df_merged.to_csv(out_path, index=False)
    logger.info("Joined dataset saved → %s (%d rows)", out_path, len(df_merged))

    return df_merged


if __name__ == "__main__":
    df = join_accident_weather()
    print(f"\nJoined dataset: {len(df):,} rows")
    weather_cols = [c for c in df.columns if "weather" in c or "temperature" in c]
    print(f"Weather columns present: {weather_cols}")
    print(df[["accident_index", "accident_date", "severity_label",
               "temperature_2m", "weather_description"]].head())
