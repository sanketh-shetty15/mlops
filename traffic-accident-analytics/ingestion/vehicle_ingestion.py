"""
ingestion/vehicle_ingestion.py
-------------------------------
Downloads (or locates) the UK STATS19 vehicle CSV for the configured year
and stores it in data/raw/vehicles/.

Key columns in the actual 2023 vehicle file:
    accident_index, accident_year, vehicle_reference,
    vehicle_type, towing_and_articulation,
    vehicle_manoeuvre, vehicle_direction_from, vehicle_direction_to,
    vehicle_location_restricted_lane,
    junction_location,
    skidding_and_overturning,
    hit_object_in_carriageway, vehicle_leaving_carriageway,
    hit_object_off_carriageway, first_point_of_impact,
    vehicle_left_hand_drive, journey_purpose_of_driver,
    sex_of_driver, age_of_driver, age_band_of_driver,
    engine_capacity_cc, propulsion_code,
    age_of_vehicle, generic_make_model,
    driver_imd_decile, driver_home_area_type,
    lsoa_of_driver
"""

import time
import json
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    VEHICLES_URL,
    VEHICLES_FILENAME,
    RAW_VEHICLES_DIR,
    HTTP_TIMEOUT_SECONDS,
    HTTP_MAX_RETRIES,
    HTTP_RETRY_BACKOFF,
    DATA_YEAR,
    get_logger,
)

logger = get_logger(__name__)


def _build_metadata(source_name, status, row_count, dest_path, error_msg=""):
    return {
        "source_name":          source_name,
        "source_type":          "csv_download",
        "extraction_timestamp": datetime.utcnow().isoformat(),
        "status":               status,
        "row_count":            row_count,
        "error_message":        error_msg,
        "destination_path":     dest_path,
    }


def _save_metadata(metadata: dict, dest_dir: Path) -> None:
    meta_path = dest_dir / "ingestion_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)


def _download_with_retry(url: str, dest_path: Path) -> None:
    for attempt in range(1, HTTP_MAX_RETRIES + 1):
        try:
            logger.info("Downloading (attempt %d/%d): %s", attempt, HTTP_MAX_RETRIES, url)
            r = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS, stream=True)
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
            logger.info("Download complete → %s", dest_path)
            return
        except requests.RequestException as exc:
            logger.warning("Attempt %d failed: %s", attempt, exc)
            if attempt < HTTP_MAX_RETRIES:
                time.sleep(HTTP_RETRY_BACKOFF * attempt)
            else:
                raise


def ingest_vehicles(force_download: bool = False) -> pd.DataFrame:
    """
    Ingest UK STATS19 vehicle records for the configured year.

    Returns pd.DataFrame with raw (unmodified) vehicle data.
    Falls back to a manually placed CSV if the download fails.
    """
    RAW_VEHICLES_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = RAW_VEHICLES_DIR / VEHICLES_FILENAME

    if dest_path.exists() and not force_download:
        logger.info("Raw vehicle file already exists — skipping download.")
    else:
        try:
            _download_with_retry(VEHICLES_URL, dest_path)
        except Exception as exc:
            logger.error("Vehicle download failed: %s", exc)
            existing = list(RAW_VEHICLES_DIR.glob("*.csv"))
            if existing:
                dest_path = existing[0]
                logger.warning("Using manually placed vehicle file: %s", dest_path)
            else:
                meta = _build_metadata(
                    f"vehicles_{DATA_YEAR}", "FAILED", 0, "", str(exc)
                )
                _save_metadata(meta, RAW_VEHICLES_DIR)
                raise FileNotFoundError(
                    f"No vehicle CSV available. Download from:\n  {VEHICLES_URL}\n"
                    f"Place in: {RAW_VEHICLES_DIR}"
                ) from exc

    logger.info("Loading vehicle CSV: %s", dest_path)
    df = pd.read_csv(dest_path, low_memory=False)
    row_count = len(df)
    logger.info("Vehicle records loaded: %d rows, %d columns", row_count, len(df.columns))

    meta = _build_metadata(
        f"vehicles_{DATA_YEAR}", "SUCCESS", row_count, str(dest_path)
    )
    _save_metadata(meta, RAW_VEHICLES_DIR)
    return df


if __name__ == "__main__":
    df = ingest_vehicles()
    print(f"\nIngested {len(df):,} vehicle records.")
    print(df.head(3).to_string())
