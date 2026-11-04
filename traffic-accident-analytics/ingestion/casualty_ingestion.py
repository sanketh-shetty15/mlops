"""
ingestion/casualty_ingestion.py
--------------------------------
Downloads (or locates) the UK STATS19 casualty CSV for the configured year
and stores it in data/raw/casualties/.

Key columns in the actual 2023 casualty file:
    accident_index, accident_year, vehicle_reference, casualty_reference,
    casualty_class,         # 1=Driver/rider, 2=Passenger, 3=Pedestrian
    sex_of_casualty,        # 1=Male, 2=Female, -1=Not known
    age_of_casualty,
    age_band_of_casualty,
    casualty_severity,      # 1=Fatal, 2=Serious, 3=Slight
    pedestrian_location,
    pedestrian_movement,
    car_passenger,
    bus_or_coach_passenger,
    pedestrian_road_maintenance_worker,
    casualty_type,
    casualty_home_area_type,
    casualty_imd_decile,
    lsoa_of_casualty
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
    CASUALTIES_URL,
    CASUALTIES_FILENAME,
    RAW_CASUALTIES_DIR,
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


def ingest_casualties(force_download: bool = False) -> pd.DataFrame:
    """
    Ingest UK STATS19 casualty records for the configured year.

    Returns pd.DataFrame with raw (unmodified) casualty data.
    Falls back to a manually placed CSV if the download fails.
    """
    RAW_CASUALTIES_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = RAW_CASUALTIES_DIR / CASUALTIES_FILENAME

    if dest_path.exists() and not force_download:
        logger.info("Raw casualty file already exists — skipping download.")
    else:
        try:
            _download_with_retry(CASUALTIES_URL, dest_path)
        except Exception as exc:
            logger.error("Casualty download failed: %s", exc)
            existing = list(RAW_CASUALTIES_DIR.glob("*.csv"))
            if existing:
                dest_path = existing[0]
                logger.warning("Using manually placed casualty file: %s", dest_path)
            else:
                meta = _build_metadata(
                    f"casualties_{DATA_YEAR}", "FAILED", 0, "", str(exc)
                )
                _save_metadata(meta, RAW_CASUALTIES_DIR)
                raise FileNotFoundError(
                    f"No casualty CSV available. Download from:\n  {CASUALTIES_URL}\n"
                    f"Place in: {RAW_CASUALTIES_DIR}"
                ) from exc

    logger.info("Loading casualty CSV: %s", dest_path)
    df = pd.read_csv(dest_path, low_memory=False)
    row_count = len(df)
    logger.info("Casualty records loaded: %d rows, %d columns", row_count, len(df.columns))

    meta = _build_metadata(
        f"casualties_{DATA_YEAR}", "SUCCESS", row_count, str(dest_path)
    )
    _save_metadata(meta, RAW_CASUALTIES_DIR)
    return df


if __name__ == "__main__":
    df = ingest_casualties()
    print(f"\nIngested {len(df):,} casualty records.")
    print(df.head(3).to_string())
