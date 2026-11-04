"""
ingestion/accident_ingestion.py
--------------------------------
Downloads (or locates) the UK STATS19 collision/accident CSV for the
configured year and copies it into data/raw/accidents/.

The DfT CSV contains one row per reported personal-injury collision.
Key columns present in the actual 2023 release:
    accident_index, accident_year, accident_reference,
    location_easting_osgr, location_northing_osgr,
    longitude, latitude,
    police_force, accident_severity,
    number_of_vehicles, number_of_casualties,
    date, day_of_week, time,
    local_authority_district, local_authority_ons_district,
    local_authority_highway, first_road_class, first_road_number,
    road_type, speed_limit, junction_detail, junction_control,
    second_road_class, second_road_number,
    pedestrian_crossing_human_control,
    pedestrian_crossing_physical_facilities,
    light_conditions, weather_conditions, road_surface_conditions,
    special_conditions_at_site, carriageway_hazards,
    urban_or_rural_area, did_police_officer_attend_scene_of_accident,
    trunk_road_flag, lsoa_of_accident_location
"""

import os
import time
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd

# Allow this script to be run directly OR imported as a module
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    ACCIDENTS_URL,
    ACCIDENTS_FILENAME,
    RAW_ACCIDENTS_DIR,
    HTTP_TIMEOUT_SECONDS,
    HTTP_MAX_RETRIES,
    HTTP_RETRY_BACKOFF,
    DATA_YEAR,
    get_logger,
)

logger = get_logger(__name__)


# ── Ingestion metadata helper ─────────────────────────────────────────────────

def _build_metadata(
    source_name: str,
    status: str,
    row_count: int,
    dest_path: str,
    error_msg: str = "",
) -> dict:
    """Return a dict that matches the ingestion_log table schema."""
    return {
        "source_name":           source_name,
        "source_type":           "csv_download",
        "extraction_timestamp":  datetime.utcnow().isoformat(),
        "status":                status,
        "row_count":             row_count,
        "error_message":         error_msg,
        "destination_path":      dest_path,
    }


def _save_metadata(metadata: dict, dest_dir: Path) -> None:
    """Persist ingestion metadata as a JSON sidecar file."""
    meta_path = dest_dir / "ingestion_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.debug("Ingestion metadata saved to %s", meta_path)


# ── Download helper ───────────────────────────────────────────────────────────

def _download_with_retry(url: str, dest_path: Path) -> None:
    """
    Download a file from *url* to *dest_path* with retry/back-off.
    Raises requests.RequestException after all retries are exhausted.
    """
    for attempt in range(1, HTTP_MAX_RETRIES + 1):
        try:
            logger.info("Downloading (attempt %d/%d): %s", attempt, HTTP_MAX_RETRIES, url)
            response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS, stream=True)
            response.raise_for_status()

            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)

            logger.info("Download complete → %s", dest_path)
            return

        except requests.RequestException as exc:
            logger.warning("Attempt %d failed: %s", attempt, exc)
            if attempt < HTTP_MAX_RETRIES:
                sleep_sec = HTTP_RETRY_BACKOFF * attempt
                logger.info("Retrying in %d seconds...", sleep_sec)
                time.sleep(sleep_sec)
            else:
                raise


# ── Public API ────────────────────────────────────────────────────────────────

def ingest_accidents(force_download: bool = False) -> pd.DataFrame:
    """
    Main entry point for accident ingestion.

    Behaviour:
    1.  If the raw CSV already exists and *force_download* is False, load it
        from disk (avoids repeated large downloads during development).
    2.  Otherwise attempt to download from the DfT URL.
    3.  If the download fails (e.g. no internet), look for a manually placed
        file in data/raw/accidents/ and load that.
    4.  Record ingestion metadata.

    Returns
    -------
    pd.DataFrame
        The raw, unmodified accident records.

    Raises
    ------
    FileNotFoundError
        If no CSV is available (download failed AND no manual file present).
    """
    RAW_ACCIDENTS_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = RAW_ACCIDENTS_DIR / ACCIDENTS_FILENAME

    # ── Step 1: check for existing file ──────────────────────────────────────
    if dest_path.exists() and not force_download:
        logger.info("Raw accident file already exists at %s — skipping download.", dest_path)
    else:
        # ── Step 2: attempt download ──────────────────────────────────────────
        try:
            _download_with_retry(ACCIDENTS_URL, dest_path)
        except Exception as exc:
            logger.error("Download failed: %s", exc)
            # ── Step 3: fall back to any CSV already in the directory ─────────
            existing = list(RAW_ACCIDENTS_DIR.glob("*.csv"))
            if existing:
                dest_path = existing[0]
                logger.warning(
                    "Using manually placed file: %s\n"
                    "To use a different year, place the CSV at:\n  %s",
                    dest_path, RAW_ACCIDENTS_DIR / ACCIDENTS_FILENAME,
                )
            else:
                meta = _build_metadata(
                    source_name=f"accidents_{DATA_YEAR}",
                    status="FAILED",
                    row_count=0,
                    dest_path="",
                    error_msg=str(exc),
                )
                _save_metadata(meta, RAW_ACCIDENTS_DIR)
                raise FileNotFoundError(
                    f"No accident CSV available. Download from:\n"
                    f"  {ACCIDENTS_URL}\n"
                    f"and place it in:\n  {RAW_ACCIDENTS_DIR}"
                ) from exc

    # ── Step 4: load and count ────────────────────────────────────────────────
    logger.info("Loading accident CSV: %s", dest_path)
    df = pd.read_csv(dest_path, low_memory=False)
    row_count = len(df)
    logger.info("Accident records loaded: %d rows, %d columns", row_count, len(df.columns))
    logger.debug("Columns: %s", list(df.columns))

    # ── Step 5: record metadata ───────────────────────────────────────────────
    meta = _build_metadata(
        source_name=f"accidents_{DATA_YEAR}",
        status="SUCCESS",
        row_count=row_count,
        dest_path=str(dest_path),
    )
    _save_metadata(meta, RAW_ACCIDENTS_DIR)

    return df


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest UK STATS19 accident data")
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download even if file already exists"
    )
    args = parser.parse_args()

    df = ingest_accidents(force_download=args.force)
    print(f"\nIngested {len(df):,} accident records.")
    print(df.head(3).to_string())
