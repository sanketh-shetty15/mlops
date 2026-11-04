"""
ingestion/weather_ingestion.py
-------------------------------
Fetches historical hourly weather from the Open-Meteo Archive API and
stores results in data/raw/weather/.

Strategy to avoid excessive API calls
--------------------------------------
The UK accident dataset can contain 100,000+ records spread across all of
Great Britain over a full year. Making one API request per accident would
be impractical (both slow and potentially rate-limited).

Instead we use a GRID-SNAPPING approach:
  1.  Round each accident's latitude and longitude to the nearest 0.5°
      grid cell (configurable via WEATHER_GRID_RESOLUTION in config.py).
  2.  Derive the unique set of (rounded_lat, rounded_lon, date) combinations
      from the accident data.
  3.  For each unique grid cell, request ALL dates that have at least one
      accident in a SINGLE API call (start_date → end_date spanning the
      whole year).
  4.  Cache each API response as a Parquet file keyed by (lat, lon).
      Subsequent runs read from cache instead of calling the API again.

The result is one Parquet file per grid cell containing 8,760 hourly rows
(one per hour of the year). This file can then be joined to accidents
by nearest-hour matching during the transformation step.

API reference: https://open-meteo.com/en/docs/historical-weather-api
Parameters used:
    temperature_2m, precipitation, rain, snowfall, weather_code,
    wind_speed_10m, wind_direction_10m, relative_humidity_2m,
    visibility, cloud_cover
"""

import time
import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Tuple

import requests
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    OPEN_METEO_BASE_URL,
    OPEN_METEO_HISTORICAL_PATH,
    OPEN_METEO_HOURLY_VARS,
    RAW_WEATHER_DIR,
    RAW_ACCIDENTS_DIR,
    ACCIDENTS_FILENAME,
    WEATHER_GRID_RESOLUTION,
    HTTP_TIMEOUT_SECONDS,
    HTTP_MAX_RETRIES,
    HTTP_RETRY_BACKOFF,
    DATA_YEAR,
    WMO_WEATHER_DESCRIPTIONS,
    get_logger,
)

logger = get_logger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def snap_to_grid(lat: float, lon: float, resolution: float = WEATHER_GRID_RESOLUTION) -> Tuple[float, float]:
    """Round lat/lon to the nearest grid cell centre."""
    import math
    # Guard against NaN inputs
    if math.isnan(lat) or math.isnan(lon):
        raise ValueError(f"NaN coordinates cannot be snapped: lat={lat}, lon={lon}")
    snapped_lat = round(round(lat / resolution) * resolution, 4)
    snapped_lon = round(round(lon / resolution) * resolution, 4)
    return snapped_lat, snapped_lon


def _nearest_hour(accident_time_str) -> int:
    """
    Given a time string 'HH:MM', return the nearest integer hour (0-23).

    Examples:
        08:37 → 9  (37 min >= 30, round up)
        08:22 → 8  (22 min < 30, round down)
        23:45 → 23 (capped at 23)
        None  → None

    This function is shared between weather_ingestion and
    join_accident_weather to avoid duplication.
    """
    import math
    if accident_time_str is None:
        return None
    try:
        s = str(accident_time_str).strip()
        if not s or s == "nan":
            return None
        # Check for float nan
        try:
            if math.isnan(float(s)):
                return None
        except (ValueError, TypeError):
            pass
        parts = s.split(":")
        hour   = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        # Use explicit round-half-up (math.floor(x+0.5)) to avoid
        # Python banker's rounding (round(0.5) == 0, round(1.5) == 2)
        fractional = hour + minute / 60
        nearest = int(math.floor(fractional + 0.5))
        return min(nearest, 23)
    except (ValueError, IndexError, AttributeError):
        return None


def _cache_path(lat: float, lon: float, year: int) -> Path:
    """Return the Parquet file path for a given grid cell + year."""
    RAW_WEATHER_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"weather_{lat}_{lon}_{year}.parquet"
    return RAW_WEATHER_DIR / fname


def _fetch_weather_for_cell(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Call the Open-Meteo historical archive API for one grid cell.

    Parameters
    ----------
    lat, lon : float
        Grid-snapped coordinates.
    start_date, end_date : str
        ISO format dates, e.g. "2023-01-01", "2023-12-31".

    Returns
    -------
    pd.DataFrame
        Hourly weather rows with columns:
        [datetime, temperature_2m, precipitation, rain, snowfall,
         weather_code, weather_description, wind_speed_10m,
         wind_direction_10m, relative_humidity_2m, visibility,
         cloud_cover, grid_lat, grid_lon]
    """
    url = f"{OPEN_METEO_BASE_URL}{OPEN_METEO_HISTORICAL_PATH}"
    params = {
        "latitude":    lat,
        "longitude":   lon,
        "start_date":  start_date,
        "end_date":    end_date,
        "hourly":      ",".join(OPEN_METEO_HOURLY_VARS),
        "timezone":    "UTC",
        "wind_speed_unit": "mph",
    }

    for attempt in range(1, HTTP_MAX_RETRIES + 1):
        try:
            logger.debug(
                "Open-Meteo request (attempt %d): lat=%.2f lon=%.2f %s→%s",
                attempt, lat, lon, start_date, end_date,
            )
            resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            break
        except requests.RequestException as exc:
            logger.warning("Open-Meteo attempt %d failed for (%.2f, %.2f): %s", attempt, lat, lon, exc)
            if attempt < HTTP_MAX_RETRIES:
                time.sleep(HTTP_RETRY_BACKOFF * attempt)
            else:
                raise

    hourly = data.get("hourly", {})
    if not hourly or "time" not in hourly:
        raise ValueError(f"Unexpected Open-Meteo response for ({lat}, {lon}): {data}")

    df = pd.DataFrame(hourly)
    df.rename(columns={"time": "datetime"}, inplace=True)
    df["datetime"] = pd.to_datetime(df["datetime"])

    # Add human-readable weather description
    df["weather_description"] = (
        df["weather_code"]
        .map(WMO_WEATHER_DESCRIPTIONS)
        .fillna("Unknown")
    )

    # Tag with grid cell
    df["grid_lat"] = lat
    df["grid_lon"] = lon

    return df


# ── Grid cell extraction from accident data ───────────────────────────────────

def _get_grid_cells_from_accidents() -> List[Tuple[float, float]]:
    """
    Load the raw accident CSV and return a deduplicated list of
    (snapped_lat, snapped_lon) grid cells covering all accidents.

    Returns an empty list with a warning if the accident CSV is not yet
    available (pipeline will still proceed but weather will be empty).
    """
    acc_path = RAW_ACCIDENTS_DIR / ACCIDENTS_FILENAME
    if not acc_path.exists():
        # Try any CSV in that folder
        existing = list(RAW_ACCIDENTS_DIR.glob("*.csv"))
        if not existing:
            logger.warning(
                "Accident CSV not found at %s. "
                "Run accident_ingestion first, or weather data will be empty.",
                acc_path,
            )
            return []
        acc_path = existing[0]

    logger.info("Reading accident coordinates from %s", acc_path)
    # Read only the lat/lon columns for efficiency
    df = pd.read_csv(acc_path, usecols=["latitude", "longitude"], low_memory=False)
    df.dropna(subset=["latitude", "longitude"], inplace=True)
    df["grid_lat"] = df["latitude"].apply(lambda x: snap_to_grid(x, 0)[0])
    df["grid_lon"] = df["longitude"].apply(lambda x: snap_to_grid(0, x)[1])

    # Fix: apply snap correctly
    snapped = df.apply(
        lambda row: snap_to_grid(row["latitude"], row["longitude"]),
        axis=1
    )
    df["grid_lat"] = snapped.apply(lambda t: t[0])
    df["grid_lon"] = snapped.apply(lambda t: t[1])

    cells = df[["grid_lat", "grid_lon"]].drop_duplicates().values.tolist()
    logger.info("Found %d unique grid cells from accident data", len(cells))
    return [(float(lat), float(lon)) for lat, lon in cells]


# ── Public API ────────────────────────────────────────────────────────────────

def ingest_weather(
    grid_cells: List[Tuple[float, float]] = None,
    start_date: str = None,
    end_date: str = None,
    force_download: bool = False,
) -> List[Path]:
    """
    Download hourly weather for all relevant grid cells.

    Parameters
    ----------
    grid_cells : list of (lat, lon) tuples, optional
        If None, derives grid cells automatically from the accident CSV.
    start_date : str, optional
        ISO format start date, e.g. "2023-01-01". Defaults to Jan 1 of DATA_YEAR.
    end_date : str, optional
        ISO format end date, e.g. "2023-12-31". Defaults to Dec 31 of DATA_YEAR.
    force_download : bool
        Re-download even if a cache file already exists.

    Returns
    -------
    list of Path
        Paths to the Parquet cache files written/found for each grid cell.
    """
    RAW_WEATHER_DIR.mkdir(parents=True, exist_ok=True)

    if start_date is None:
        start_date = f"{DATA_YEAR}-01-01"
    if end_date is None:
        end_date = f"{DATA_YEAR}-12-31"

    if grid_cells is None:
        grid_cells = _get_grid_cells_from_accidents()

    if not grid_cells:
        logger.warning("No grid cells to process. Weather ingestion skipped.")
        return []

    logger.info(
        "Starting weather ingestion: %d grid cells, %s → %s",
        len(grid_cells), start_date, end_date,
    )

    written_paths: List[Path] = []
    total = len(grid_cells)

    for idx, (lat, lon) in enumerate(grid_cells, start=1):
        cache = _cache_path(lat, lon, DATA_YEAR)

        if cache.exists() and not force_download:
            logger.info("[%d/%d] Cache hit — skipping API call for (%.2f, %.2f)", idx, total, lat, lon)
            written_paths.append(cache)
            continue

        try:
            logger.info("[%d/%d] Fetching weather for grid cell (%.2f, %.2f)", idx, total, lat, lon)
            df = _fetch_weather_for_cell(lat, lon, start_date, end_date)
            df.to_parquet(cache, index=False)
            logger.info("  → Saved %d hourly rows to %s", len(df), cache)
            written_paths.append(cache)

            # Polite pause between API calls to avoid rate limiting
            if idx < total:
                time.sleep(0.5)

        except Exception as exc:
            logger.error(
                "Weather fetch FAILED for (%.2f, %.2f): %s — skipping this cell.",
                lat, lon, exc,
            )
            # We continue: missing weather is non-fatal; accidents will get NULL weather

    # Write a summary metadata file
    meta = {
        "source_name":          f"weather_{DATA_YEAR}",
        "source_type":          "api_open_meteo",
        "extraction_timestamp": datetime.utcnow().isoformat(),
        "status":               "SUCCESS" if written_paths else "PARTIAL",
        "grid_cells_requested": total,
        "grid_cells_fetched":   len(written_paths),
        "start_date":           start_date,
        "end_date":             end_date,
        "hourly_variables":     OPEN_METEO_HOURLY_VARS,
    }
    meta_path = RAW_WEATHER_DIR / "ingestion_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info(
        "Weather ingestion complete: %d/%d cells fetched.",
        len(written_paths), total,
    )
    return written_paths


def load_all_weather() -> pd.DataFrame:
    """
    Load all cached weather Parquet files into a single DataFrame.

    Used by the transformation layer to join with accident data.

    Returns
    -------
    pd.DataFrame
        Combined hourly weather for all cached grid cells, or empty
        DataFrame if no cache exists yet.
    """
    files = list(RAW_WEATHER_DIR.glob("weather_*.parquet"))
    if not files:
        logger.warning("No weather Parquet files found in %s", RAW_WEATHER_DIR)
        return pd.DataFrame()

    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_parquet(f))
        except Exception as exc:
            logger.warning("Could not read %s: %s", f, exc)

    combined = pd.concat(dfs, ignore_index=True)
    logger.info("Loaded %d hourly weather rows from %d files", len(combined), len(files))
    return combined


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest weather data from Open-Meteo")
    parser.add_argument("--force", action="store_true", help="Re-download cached cells")
    parser.add_argument("--start-date", default=None, help="ISO start date, e.g. 2023-01-01")
    parser.add_argument("--end-date", default=None, help="ISO end date, e.g. 2023-12-31")
    args = parser.parse_args()

    paths = ingest_weather(
        start_date=args.start_date,
        end_date=args.end_date,
        force_download=args.force,
    )
    print(f"\nWeather ingestion complete. {len(paths)} grid cell cache files written.")
