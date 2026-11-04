"""
config/config.py
----------------
Central configuration module for the Traffic Accident Analytics pipeline.

Reads all settings from environment variables (via .env file).
Import this module wherever configuration is needed.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# ── PostgreSQL ────────────────────────────────────────────────────────────────
#
# Two ways to configure the database connection:
#
# OPTION A — DATABASE_URL (recommended for Neon and other cloud providers)
#   Set DATABASE_URL in .env to a full postgresql:// connection string.
#   Example (Neon):
#     DATABASE_URL=postgresql://user:pass@ep-xxx.aws.neon.tech/neondb?sslmode=require
#
# OPTION B — Individual fields (for local PostgreSQL)
#   Set POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER,
#   POSTGRES_PASSWORD, POSTGRES_SSLMODE in .env.
#
# DATABASE_URL takes priority over individual fields if both are set.

DATABASE_URL = os.getenv("DATABASE_URL", "")

POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT     = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB       = os.getenv("POSTGRES_DB", "traffic_accidents")
POSTGRES_USER     = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
# sslmode=require is mandatory for Neon; use 'disable' for local dev if needed
POSTGRES_SSLMODE  = os.getenv("POSTGRES_SSLMODE", "require")


def _parse_database_url(url: str) -> dict:
    """
    Parse a postgresql://user:pass@host:port/dbname?sslmode=require URL
    into a dict of psycopg2 keyword arguments.

    Handles Neon's format which may include a query string (?sslmode=...).
    """
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    params = {
        "host":     parsed.hostname,
        "port":     parsed.port or 5432,
        "dbname":   parsed.path.lstrip("/"),
        "user":     parsed.username,
        "password": parsed.password,
        "sslmode":  "require",          # safe default for cloud DBs
    }
    # Override sslmode if explicitly set in the query string
    qs = parse_qs(parsed.query)
    if "sslmode" in qs:
        params["sslmode"] = qs["sslmode"][0]

    return params


def get_db_connection_string() -> str:
    """
    Return a psycopg2 keyword-argument connection string.

    Uses DATABASE_URL if set (Neon / cloud), otherwise falls back to
    the individual POSTGRES_* environment variables.
    """
    if DATABASE_URL:
        p = _parse_database_url(DATABASE_URL)
        return (
            f"host={p['host']} "
            f"port={p['port']} "
            f"dbname={p['dbname']} "
            f"user={p['user']} "
            f"password={p['password']} "
            f"sslmode={p['sslmode']}"
        )
    # Local / individual-field fallback
    conn = (
        f"host={POSTGRES_HOST} "
        f"port={POSTGRES_PORT} "
        f"dbname={POSTGRES_DB} "
        f"user={POSTGRES_USER} "
        f"password={POSTGRES_PASSWORD}"
    )
    if POSTGRES_SSLMODE:
        conn += f" sslmode={POSTGRES_SSLMODE}"
    return conn


def get_sqlalchemy_url() -> str:
    """
    Return a SQLAlchemy database URL for pandas read_sql / to_sql.

    For Neon the URL must include ?sslmode=require in the query string
    so that SQLAlchemy passes it through to psycopg2.
    """
    if DATABASE_URL:
        # SQLAlchemy needs the postgresql+psycopg2:// scheme prefix.
        # Replace postgresql:// or postgres:// with postgresql+psycopg2://
        url = DATABASE_URL
        for scheme in ("postgresql://", "postgres://"):
            if url.startswith(scheme):
                url = "postgresql+psycopg2://" + url[len(scheme):]
                break
        # Ensure sslmode is present in the query string
        if "sslmode" not in url:
            sep = "&" if "?" in url else "?"
            url = url + sep + "sslmode=require"
        return url

    # Local fallback
    base = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    if POSTGRES_SSLMODE and POSTGRES_SSLMODE != "disable":
        base += f"?sslmode={POSTGRES_SSLMODE}"
    return base

# ── Open-Meteo ────────────────────────────────────────────────────────────────
OPEN_METEO_BASE_URL = os.getenv(
    "OPEN_METEO_BASE_URL",
    "https://archive-api.open-meteo.com"
)
# Historical endpoint path
OPEN_METEO_HISTORICAL_PATH = "/v1/archive"

# Weather variables requested from the API
OPEN_METEO_HOURLY_VARS = [
    "temperature_2m",
    "precipitation",
    "rain",
    "snowfall",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
    "relative_humidity_2m",
    "visibility",
    "cloud_cover",
]

# ── Data directories ──────────────────────────────────────────────────────────
_DATA_DIR = Path(os.getenv("DATA_DIR", str(_PROJECT_ROOT / "data")))

RAW_DIR        = _DATA_DIR / "raw"
STAGING_DIR    = _DATA_DIR / "staging"
CLEANED_DIR    = _DATA_DIR / "cleaned"
REJECTED_DIR   = _DATA_DIR / "rejected"

RAW_ACCIDENTS_DIR  = RAW_DIR / "accidents"
RAW_VEHICLES_DIR   = RAW_DIR / "vehicles"
RAW_CASUALTIES_DIR = RAW_DIR / "casualties"
RAW_WEATHER_DIR    = RAW_DIR / "weather"

# ── UK Road Safety dataset ────────────────────────────────────────────────────
DATA_YEAR = int(os.getenv("DATA_YEAR", "2023"))

# Base URL for the DfT open data page
DFT_BASE_URL = "https://data.dft.gov.uk/road-accidents-safety-data"

# Expected filenames on the DfT server
ACCIDENTS_FILENAME  = f"dft-road-casualty-statistics-collision-{DATA_YEAR}.csv"
VEHICLES_FILENAME   = f"dft-road-casualty-statistics-vehicle-{DATA_YEAR}.csv"
CASUALTIES_FILENAME = f"dft-road-casualty-statistics-casualty-{DATA_YEAR}.csv"

ACCIDENTS_URL  = f"{DFT_BASE_URL}/{ACCIDENTS_FILENAME}"
VEHICLES_URL   = f"{DFT_BASE_URL}/{VEHICLES_FILENAME}"
CASUALTIES_URL = f"{DFT_BASE_URL}/{CASUALTIES_FILENAME}"

# ── Severity mapping (STATS19 coded values → human-readable) ──────────────────
# 1 = Fatal, 2 = Serious, 3 = Slight
SEVERITY_MAP = {1: "Fatal", 2: "Serious", 3: "Slight"}
VALID_SEVERITIES = {1, 2, 3}

# ── Road-type mapping (STATS19 coded values) ──────────────────────────────────
ROAD_TYPE_MAP = {
    1: "Roundabout",
    2: "One way street",
    3: "Dual carriageway",
    6: "Single carriageway",
    7: "Slip road",
    9: "Unknown",
    12: "One way street/Slip road",
}

# ── Weather-code descriptions (WMO codes returned by Open-Meteo) ──────────────
WMO_WEATHER_DESCRIPTIONS = {
    0:  "Clear sky",
    1:  "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

# ── Data quality thresholds ───────────────────────────────────────────────────
LAT_MIN, LAT_MAX   = -90.0,  90.0
LON_MIN, LON_MAX   = -180.0, 180.0
# UK bounding box (used for soft validation / warning)
UK_LAT_MIN, UK_LAT_MAX = 49.8, 60.9
UK_LON_MIN, UK_LON_MAX = -8.2, 1.8

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger for use across the pipeline.

    Usage:
        from config.config import get_logger
        logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    return logger

# ── Ingestion metadata ────────────────────────────────────────────────────────
# Table name in PostgreSQL that records pipeline run history
INGESTION_LOG_TABLE = "ingestion_log"

# ── Pipeline retry settings ───────────────────────────────────────────────────
HTTP_TIMEOUT_SECONDS  = 60
HTTP_MAX_RETRIES      = 3
HTTP_RETRY_BACKOFF    = 2   # seconds between retries (doubles each attempt)

# ── Weather API batching ──────────────────────────────────────────────────────
# Number of unique (lat, lon) grid cells to query in one pipeline run.
# Accidents are snapped to a 0.5° grid to reduce total API calls.
WEATHER_GRID_RESOLUTION = 0.5   # degrees

# ══════════════════════════════════════════════════════════════
# PART 2 — MLOps Extension Settings
# ══════════════════════════════════════════════════════════════

# ── MLflow ────────────────────────────────────────────────────
# Local SQLite tracking store — no server needed for development
_MLFLOW_DIR = _PROJECT_ROOT / "mlflow"
MLFLOW_TRACKING_URI  = os.getenv(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{_MLFLOW_DIR}/mlflow.db"
)
MLFLOW_EXPERIMENT_NAME = os.getenv(
    "MLFLOW_EXPERIMENT_NAME",
    "traffic_accident_severity"
)
MLFLOW_REGISTERED_MODEL_NAME = "accident_severity_classifier"

# ── Model artefact paths ──────────────────────────────────────
MODELS_DIR          = _PROJECT_ROOT / "models"
BEST_MODEL_PATH     = MODELS_DIR / "best_model.pkl"
PREPROCESSOR_PATH   = MODELS_DIR / "preprocessor.pkl"
FEATURE_NAMES_PATH  = MODELS_DIR / "feature_names.json"
CLASS_REPORT_PATH   = MODELS_DIR / "classification_report.json"

# ── Feature definition ────────────────────────────────────────
# These are the columns from accidents_with_weather.csv used as
# model INPUT features.  Do NOT include the target column here.
ML_FEATURE_COLUMNS = [
    "accident_hour",           # 0-23
    "weekday_num",             # 0=Monday … 6=Sunday
    "accident_month",          # 1-12
    "road_type",               # STATS19 coded integer
    "speed_limit",             # mph
    "junction_detail",         # STATS19 coded integer
    "light_conditions",        # STATS19 coded integer
    "road_surface_conditions", # STATS19 coded integer
    "urban_or_rural_area",     # 1=Urban, 2=Rural
    "number_of_vehicles",      # integer count
    "number_of_casualties",    # integer count
    "temperature_2m",          # °C from Open-Meteo
    "precipitation",           # mm from Open-Meteo
    "wind_speed_10m",          # mph from Open-Meteo
    "weather_code",            # WMO code from Open-Meteo
]

# Target column
ML_TARGET_COLUMN = "accident_severity"   # 1=Fatal, 2=Serious, 3=Slight

# Class label mapping for display
ML_CLASS_NAMES = {1: "Fatal", 2: "Serious", 3: "Slight"}
ML_CLASS_ORDER = [1, 2, 3]   # ordered from most to least severe

# ── Train / Validation / Test split (chronological) ──────────
# Jan-Aug 2023  → Train   (~67%)
# Sep-Oct 2023  → Val     (~17%)
# Nov-Dec 2023  → Test    (~16%)
TRAIN_END_MONTH   = 8    # inclusive  (August)
VAL_END_MONTH     = 10   # inclusive  (October)
# November-December automatically becomes test set

# ── Model hyperparameters ─────────────────────────────────────
RF_PARAMS = {
    "n_estimators":     100,   # reduced from 300 — ~3× faster inference
    "max_depth":        10,    # reduced from 15 — shallower trees, faster
    "min_samples_leaf": 5,
    "class_weight":     "balanced",
    "random_state":     42,
    "n_jobs":           -1,
}

XGB_PARAMS = {
    "n_estimators":     150,   # reduced from 300
    "max_depth":        6,
    "learning_rate":    0.05,
    "subsample":        0.8,
    "colsample_bytree": 0.8,
    "eval_metric":      "mlogloss",
    "random_state":     42,
    "use_label_encoder": False,
}

LGBM_PARAMS = {
    "n_estimators":   150,     # reduced from 300
    "max_depth":      6,       # reduced from 8
    "learning_rate":  0.05,
    "num_leaves":     31,      # reduced from 63 — simpler tree structure
    "class_weight":   "balanced",
    "random_state":   42,
    "n_jobs":         -1,
    "verbose":        -1,
}

# ── Champion selection thresholds ─────────────────────────────
# Primary metric: macro-F1
# Tie-break: Fatal recall
MIN_ACCEPTABLE_MACRO_F1   = 0.35  # reject models below this
MIN_ACCEPTABLE_FATAL_RECALL = 0.20  # warn if Fatal recall < this

# ── Retraining thresholds ─────────────────────────────────────
RETRAIN_MACRO_F1_THRESHOLD      = 0.30   # retrain if F1 drops below
RETRAIN_FN_RATE_THRESHOLD       = 0.50   # retrain if >50% Fatal missed
RETRAIN_DRIFT_PVALUE_THRESHOLD  = 0.05   # retrain on KS-test p < 0.05

# ── FastAPI settings ──────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
