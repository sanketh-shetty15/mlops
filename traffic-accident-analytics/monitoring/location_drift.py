"""
monitoring/location_drift.py
------------------------------
Detects geographic drift — whether accidents are occurring in new
locations compared to the training data.

Why does location drift matter?
--------------------------------
The model was trained on accidents across Great Britain in Jan-Aug 2023.
If the deployment dataset comes from a different region or time period,
the model may not generalise well to the new geographic distribution.

Method
------
1. Compare latitude distributions  → KS-test
2. Compare longitude distributions → KS-test
3. Compare grid cell coverage      → new cells in recent data not seen in training

Usage
-----
    python monitoring/location_drift.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    CLEANED_DIR,
    MODELS_DIR,
    TRAIN_END_MONTH,
    RETRAIN_DRIFT_PVALUE_THRESHOLD,
    WEATHER_GRID_RESOLUTION,
    get_logger,
)

logger = get_logger(__name__)


def _snap_to_grid(lat: float, lon: float,
                  resolution: float = WEATHER_GRID_RESOLUTION) -> tuple:
    """Snap coordinates to the nearest grid cell."""
    import math
    if math.isnan(lat) or math.isnan(lon):
        return (None, None)
    snapped_lat = round(round(lat / resolution) * resolution, 4)
    snapped_lon = round(round(lon / resolution) * resolution, 4)
    return (snapped_lat, snapped_lon)


def run_location_drift(recent_csv: str = None) -> dict:
    """
    Compare geographic distributions of training vs recent accidents.

    Returns dict with:
        lat_ks, lat_p       — KS-test on latitude
        lon_ks, lon_p       — KS-test on longitude
        new_grid_cells      — grid cells in recent but not in training
        coverage_pct        — % of recent cells seen during training
        location_drifted    — True if significant drift
        retrain_required    — True if drift exceeds threshold
    """
    # Load training data
    base_path = CLEANED_DIR / "accidents_with_weather.csv"
    if not base_path.exists():
        base_path = CLEANED_DIR / "accidents_cleaned.csv"

    df = pd.read_csv(base_path, low_memory=False)
    df["accident_date"] = pd.to_datetime(df["accident_date"], errors="coerce")

    df_train  = df[df["accident_date"].dt.month <= TRAIN_END_MONTH].copy()

    if recent_csv and Path(recent_csv).exists():
        df_recent = pd.read_csv(recent_csv, low_memory=False)
        df_recent["accident_date"] = pd.to_datetime(
            df_recent["accident_date"], errors="coerce"
        )
    else:
        df_recent = df[df["accident_date"].dt.month > 10].copy()  # Nov-Dec

    logger.info(
        "Location drift check: train=%d rows, recent=%d rows",
        len(df_train), len(df_recent)
    )

    # ── KS-test on lat/lon ────────────────────────────────────────────────────
    train_lat  = df_train["latitude"].dropna().values
    recent_lat = df_recent["latitude"].dropna().values
    train_lon  = df_train["longitude"].dropna().values
    recent_lon = df_recent["longitude"].dropna().values

    lat_ks, lat_p = ks_2samp(train_lat, recent_lat)
    lon_ks, lon_p = ks_2samp(train_lon, recent_lon)

    lat_drifted = bool(lat_p < RETRAIN_DRIFT_PVALUE_THRESHOLD)
    lon_drifted = bool(lon_p < RETRAIN_DRIFT_PVALUE_THRESHOLD)

    # ── Grid cell coverage ────────────────────────────────────────────────────
    train_cells = set(
        _snap_to_grid(row.latitude, row.longitude)
        for row in df_train[["latitude", "longitude"]].dropna().itertuples()
    )
    recent_cells = set(
        _snap_to_grid(row.latitude, row.longitude)
        for row in df_recent[["latitude", "longitude"]].dropna().itertuples()
    )
    train_cells.discard((None, None))
    recent_cells.discard((None, None))

    new_cells        = recent_cells - train_cells
    coverage_pct     = float(
        100 * len(recent_cells & train_cells) / max(len(recent_cells), 1)
    )

    location_drifted = lat_drifted or lon_drifted or (len(new_cells) > 10)
    retrain_required = location_drifted

    summary = {
        "run_timestamp":    datetime.utcnow().isoformat(),
        "train_rows":       int(len(df_train)),
        "recent_rows":      int(len(df_recent)),
        "lat_ks_statistic": round(float(lat_ks), 4),
        "lat_p_value":      round(float(lat_p), 6),
        "lat_drifted":      lat_drifted,
        "lon_ks_statistic": round(float(lon_ks), 4),
        "lon_p_value":      round(float(lon_p), 6),
        "lon_drifted":      lon_drifted,
        "train_grid_cells": int(len(train_cells)),
        "recent_grid_cells":int(len(recent_cells)),
        "new_grid_cells":   int(len(new_cells)),
        "coverage_pct":     round(coverage_pct, 2),
        "location_drifted": location_drifted,
        "retrain_required": retrain_required,
    }

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODELS_DIR / "location_drift_report.json", "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Location drift report saved → %s",
                MODELS_DIR / "location_drift_report.json")

    if location_drifted:
        logger.warning(
            "LOCATION DRIFT detected! lat_p=%.4f lon_p=%.4f "
            "new_cells=%d coverage=%.1f%%",
            lat_p, lon_p, len(new_cells), coverage_pct
        )
    else:
        logger.info(
            "No location drift. lat_p=%.4f lon_p=%.4f "
            "new_cells=%d coverage=%.1f%%",
            lat_p, lon_p, len(new_cells), coverage_pct
        )

    return summary


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    report = run_location_drift()
    print(f"\nLocation drift check:")
    print(f"  Latitude  KS={report['lat_ks_statistic']:.4f}  p={report['lat_p_value']:.4f}"
          f"  drifted={report['lat_drifted']}")
    print(f"  Longitude KS={report['lon_ks_statistic']:.4f}  p={report['lon_p_value']:.4f}"
          f"  drifted={report['lon_drifted']}")
    print(f"  New grid cells : {report['new_grid_cells']}")
    print(f"  Coverage       : {report['coverage_pct']:.1f}%")
    print(f"  Retrain        : {report['retrain_required']}")
