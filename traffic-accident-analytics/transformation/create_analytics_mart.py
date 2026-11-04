"""
transformation/create_analytics_mart.py
-----------------------------------------
Builds the PostgreSQL star schema and analytical data mart.

Uses psycopg2.extras.execute_values for batch inserts (10k rows/batch)
which is ~100x faster than row-by-row inserts and avoids Neon timeouts.

Tables populated:
  dim_severity, dim_date, dim_location, dim_road, dim_weather
  fact_accident
  accident_analytics_mart
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import psycopg2
import psycopg2.extras
from datetime import datetime

from config.config import (
    CLEANED_DIR,
    get_db_connection_string,
    SEVERITY_MAP,
    ROAD_TYPE_MAP,
    get_logger,
)

logger = get_logger(__name__)

BATCH_SIZE = 5_000   # rows per execute_values call


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(get_db_connection_string())


def _v(val):
    """Return Python-native value or None — safe for psycopg2."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    return val


def _vi(val):
    v = _v(val)
    return None if v is None else int(v)


def _vf(val):
    v = _v(val)
    return None if v is None else float(v)


def _vs(val, maxlen=255):
    v = _v(val)
    return None if v is None else str(v)[:maxlen]


def _batch_insert(conn, sql: str, rows: list, label: str) -> int:
    """
    Insert rows in batches using execute_values.
    Returns total rows inserted.
    """
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, batch, page_size=BATCH_SIZE)
        conn.commit()
        total += len(batch)
        logger.info("  %s: %d / %d rows loaded", label, total, len(rows))
    return total


# ── Source data loaders ────────────────────────────────────────────────────────

def _load_joined_accidents() -> pd.DataFrame:
    path = CLEANED_DIR / "accidents_with_weather.csv"
    if not path.exists():
        path = CLEANED_DIR / "accidents_cleaned.csv"
        logger.warning("Weather-joined file not found; using %s", path)
    if not path.exists():
        raise FileNotFoundError(f"No cleaned accident data at {path}")
    df = pd.read_csv(path, low_memory=False)
    logger.info("Loaded joined accidents: %d rows", len(df))
    return df


# ── Dimension builders ─────────────────────────────────────────────────────────

def _build_dim_severity() -> pd.DataFrame:
    return pd.DataFrame([
        {"severity_id": k, "severity_name": v} for k, v in SEVERITY_MAP.items()
    ])


def _build_dim_date(df: pd.DataFrame) -> pd.DataFrame:
    if "accident_date" not in df.columns:
        return pd.DataFrame()
    dates = pd.to_datetime(df["accident_date"], errors="coerce").dropna().unique()
    records = []
    for dt in sorted(dates):
        dt = pd.Timestamp(dt)
        records.append({
            "full_date":    dt.date(),
            "year":         dt.year,
            "month":        dt.month,
            "month_name":   dt.strftime("%B"),
            "day":          dt.day,
            "weekday":      dt.dayofweek,
            "weekday_name": dt.strftime("%A"),
            "quarter":      dt.quarter,
        })
    return pd.DataFrame(records).drop_duplicates(subset=["full_date"])


def _build_dim_location(df: pd.DataFrame) -> pd.DataFrame:
    loc_cols = [c for c in ["latitude", "longitude",
                             "urban_or_rural_area", "local_authority_district"]
                if c in df.columns]
    df_loc = df[loc_cols].copy().drop_duplicates(
        subset=["latitude", "longitude"]
    ).dropna(subset=["latitude", "longitude"])
    df_loc.rename(columns={
        "urban_or_rural_area":      "urban_rural_code",
        "local_authority_district": "local_authority_code",
    }, inplace=True)
    return df_loc.reset_index(drop=True)


def _build_dim_road(df: pd.DataFrame) -> pd.DataFrame:
    road_cols = [c for c in ["road_type", "speed_limit",
                              "junction_detail", "junction_control",
                              "first_road_class"] if c in df.columns]
    df_road = df[road_cols].copy().drop_duplicates().dropna(subset=["road_type"])
    df_road["road_type_name"] = df_road["road_type"].map(ROAD_TYPE_MAP)
    return df_road.reset_index(drop=True)


def _build_dim_weather(df: pd.DataFrame) -> pd.DataFrame:
    wx_cols = [c for c in ["weather_code", "weather_description"] if c in df.columns]
    if not wx_cols:
        return pd.DataFrame()
    df_wx = df[wx_cols].copy().drop_duplicates(subset=["weather_code"]).dropna(
        subset=["weather_code"]
    )
    return df_wx.reset_index(drop=True)


# ── PostgreSQL loaders (batch version) ────────────────────────────────────────

def _load_dim_severity(conn, df: pd.DataFrame) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE dim_severity RESTART IDENTITY CASCADE;")
    conn.commit()
    rows = [(_vi(r["severity_id"]), _vs(r["severity_name"])) for _, r in df.iterrows()]
    sql = """
        INSERT INTO dim_severity (severity_id, severity_name)
        VALUES %s
        ON CONFLICT (severity_id) DO UPDATE SET severity_name = EXCLUDED.severity_name
    """
    _batch_insert(conn, sql, rows, "dim_severity")
    logger.info("dim_severity loaded (%d rows)", len(df))


def _load_dim_date(conn, df: pd.DataFrame) -> dict:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE dim_date RESTART IDENTITY CASCADE;")
    conn.commit()

    rows = [
        (
            r["full_date"], _vi(r["year"]), _vi(r["month"]), _vs(r["month_name"]),
            _vi(r["day"]), _vi(r["weekday"]), _vs(r["weekday_name"]), _vi(r["quarter"]),
        )
        for _, r in df.iterrows()
    ]
    sql = """
        INSERT INTO dim_date (full_date, year, month, month_name, day, weekday, weekday_name, quarter)
        VALUES %s
        ON CONFLICT (full_date) DO NOTHING
    """
    _batch_insert(conn, sql, rows, "dim_date")
    logger.info("dim_date loaded (%d rows)", len(df))

    # Build date_id map by querying back
    with conn.cursor() as cur:
        cur.execute("SELECT date_id, full_date FROM dim_date;")
        return {str(row[1]): row[0] for row in cur.fetchall()}


def _load_dim_location(conn, df: pd.DataFrame) -> dict:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE dim_location RESTART IDENTITY CASCADE;")
    conn.commit()

    rows = [
        (
            _vf(r.get("latitude")), _vf(r.get("longitude")),
            _vi(r.get("urban_rural_code")), _vi(r.get("local_authority_code")),
        )
        for _, r in df.iterrows()
        if _vf(r.get("latitude")) is not None and _vf(r.get("longitude")) is not None
    ]
    sql = """
        INSERT INTO dim_location (latitude, longitude, urban_rural_code, local_authority_code)
        VALUES %s
        ON CONFLICT (latitude, longitude) DO NOTHING
    """
    _batch_insert(conn, sql, rows, "dim_location")
    logger.info("dim_location loaded (%d rows)", len(df))

    # Build location_id map
    with conn.cursor() as cur:
        cur.execute("SELECT location_id, latitude, longitude FROM dim_location;")
        return {(float(row[1]), float(row[2])): row[0] for row in cur.fetchall()}


def _load_dim_road(conn, df: pd.DataFrame) -> dict:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE dim_road RESTART IDENTITY CASCADE;")
    conn.commit()

    seen = set()
    rows = []
    for _, r in df.iterrows():
        rt = _vi(r.get("road_type"))
        if rt is None or rt in seen:
            continue
        seen.add(rt)
        rows.append((
            rt,
            _vs(r.get("road_type_name")),
            _vi(r.get("speed_limit")),
            _vi(r.get("junction_detail")),
            _vi(r.get("junction_control")),
            _vi(r.get("first_road_class")),
        ))
    sql = """
        INSERT INTO dim_road (road_type_code, road_type_name, speed_limit,
                              junction_detail, junction_control, first_road_class)
        VALUES %s
        ON CONFLICT (road_type_code) DO NOTHING
    """
    _batch_insert(conn, sql, rows, "dim_road")
    logger.info("dim_road loaded (%d rows)", len(rows))

    with conn.cursor() as cur:
        cur.execute("SELECT road_id, road_type_code FROM dim_road;")
        return {row[1]: row[0] for row in cur.fetchall()}


def _load_dim_weather(conn, df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE dim_weather RESTART IDENTITY CASCADE;")
    conn.commit()

    rows = [
        (_vi(r.get("weather_code")), _vs(r.get("weather_description")))
        for _, r in df.iterrows()
        if _vi(r.get("weather_code")) is not None
    ]
    sql = """
        INSERT INTO dim_weather (weather_code, weather_description)
        VALUES %s
        ON CONFLICT (weather_code) DO NOTHING
    """
    _batch_insert(conn, sql, rows, "dim_weather")
    logger.info("dim_weather loaded (%d rows)", len(rows))

    with conn.cursor() as cur:
        cur.execute("SELECT weather_id, weather_code FROM dim_weather;")
        return {row[1]: row[0] for row in cur.fetchall()}


def _load_fact_accident(conn, df, date_map, loc_map, road_map, wx_map) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE fact_accident RESTART IDENTITY CASCADE;")
    conn.commit()

    rows = []
    skipped = 0
    for _, row in df.iterrows():
        acc_date_raw = row.get("accident_date")
        try:
            acc_date_str = str(pd.to_datetime(acc_date_raw, errors="coerce").date())
        except Exception:
            skipped += 1
            continue

        date_id     = date_map.get(acc_date_str)
        lat         = _vf(row.get("latitude"))
        lon         = _vf(row.get("longitude"))
        location_id = loc_map.get((lat, lon)) if lat and lon else None

        if date_id is None or location_id is None:
            skipped += 1
            continue

        road_id    = road_map.get(_vi(row.get("road_type")))
        wx_code    = _vi(row.get("weather_code"))
        weather_id = wx_map.get(wx_code)

        rows.append((
            _vs(row.get("accident_index")),
            date_id, location_id, road_id, weather_id,
            _vi(row.get("accident_severity")),
            _vi(row.get("number_of_vehicles")),
            _vi(row.get("number_of_casualties")),
            _vi(row.get("accident_hour")),
            _vi(row.get("speed_limit")),
            _vi(row.get("light_conditions")),
            _vi(row.get("road_surface_conditions")),
            _vi(row.get("urban_or_rural_area")),
            _vf(row.get("temperature_2m")),
            _vf(row.get("precipitation")),
            _vf(row.get("wind_speed_10m")),
            _vs(row.get("weather_description")),
        ))

    sql = """
        INSERT INTO fact_accident (
            accident_index, date_id, location_id, road_id,
            weather_id, severity_id, vehicle_count, casualty_count,
            accident_hour, speed_limit, light_conditions,
            road_surface_conditions, urban_rural_area,
            temperature_2m, precipitation, wind_speed_10m,
            weather_description
        ) VALUES %s
        ON CONFLICT (accident_index) DO NOTHING
    """
    inserted = _batch_insert(conn, sql, rows, "fact_accident")
    logger.info("fact_accident: %d inserted, %d skipped (missing FK)", inserted, skipped)


def _load_analytics_mart(conn, df: pd.DataFrame) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE accident_analytics_mart;")
    conn.commit()

    rows = []
    for _, row in df.iterrows():
        acc_date = pd.to_datetime(row.get("accident_date"), errors="coerce")
        if pd.isna(acc_date):
            continue
        rows.append((
            _vs(row.get("accident_index")),
            acc_date.date(),
            acc_date.year,
            acc_date.month,
            acc_date.strftime("%B"),
            acc_date.dayofweek,
            acc_date.strftime("%A"),
            _vi(row.get("accident_hour")),
            _vf(row.get("latitude")),
            _vf(row.get("longitude")),
            _vi(row.get("accident_severity")),
            _vs(row.get("severity_label")),
            _vi(row.get("road_type")),
            _vs(ROAD_TYPE_MAP.get(_vi(row.get("road_type")))),
            _vi(row.get("speed_limit")),
            _vi(row.get("junction_detail")),
            _vi(row.get("light_conditions")),
            _vi(row.get("road_surface_conditions")),
            _vi(row.get("urban_or_rural_area")),
            _vi(row.get("number_of_vehicles")),
            _vi(row.get("number_of_casualties")),
            _vf(row.get("temperature_2m")),
            _vf(row.get("precipitation")),
            _vf(row.get("wind_speed_10m")),
            _vi(row.get("weather_code")),
            _vs(row.get("weather_description")),
            bool(row.get("weather_matched", False)),
        ))

    sql = """
        INSERT INTO accident_analytics_mart (
            accident_index, accident_date, year, month, month_name,
            weekday, weekday_name, accident_hour,
            latitude, longitude,
            severity_code, severity_label,
            road_type_code, road_type_name, speed_limit,
            junction_detail, light_conditions, road_surface_conditions,
            urban_rural_area,
            number_of_vehicles, number_of_casualties,
            temperature_2m, precipitation, wind_speed_10m,
            weather_code, weather_description,
            weather_matched
        ) VALUES %s
        ON CONFLICT (accident_index) DO UPDATE SET
            accident_date       = EXCLUDED.accident_date,
            temperature_2m      = EXCLUDED.temperature_2m,
            weather_description = EXCLUDED.weather_description
    """
    inserted = _batch_insert(conn, sql, rows, "accident_analytics_mart")
    logger.info("accident_analytics_mart: %d rows loaded", inserted)


# ── Main entry point ───────────────────────────────────────────────────────────

def build_analytics_mart() -> None:
    """
    Full pipeline: load cleaned data → build dims → load fact → load mart.
    Safe to re-run: TRUNCATE + batch INSERT with ON CONFLICT handling.
    """
    logger.info("=== Building analytical data mart ===")

    df_acc = _load_joined_accidents()

    dim_severity = _build_dim_severity()
    dim_date     = _build_dim_date(df_acc)
    dim_location = _build_dim_location(df_acc)
    dim_road     = _build_dim_road(df_acc)
    dim_weather  = _build_dim_weather(df_acc)

    logger.info(
        "Dimensions: severity=%d, date=%d, location=%d, road=%d, weather=%d",
        len(dim_severity), len(dim_date), len(dim_location),
        len(dim_road), len(dim_weather),
    )

    try:
        conn = _get_conn()
        logger.info("Connected to PostgreSQL/Neon.")

        _load_dim_severity(conn, dim_severity)
        date_map = _load_dim_date(conn, dim_date)
        loc_map  = _load_dim_location(conn, dim_location)
        road_map = _load_dim_road(conn, dim_road)
        wx_map   = _load_dim_weather(conn, dim_weather)

        _load_fact_accident(conn, df_acc, date_map, loc_map, road_map, wx_map)
        _load_analytics_mart(conn, df_acc)

        conn.close()
        logger.info("=== Analytical data mart build COMPLETE ===")

    except psycopg2.OperationalError as exc:
        logger.error("PostgreSQL connection failed: %s", exc)
        raise


if __name__ == "__main__":
    build_analytics_mart()
