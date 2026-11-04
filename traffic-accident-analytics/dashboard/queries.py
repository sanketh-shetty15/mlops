"""
dashboard/queries.py
---------------------
All SQL queries used by the Streamlit dashboard.

Each function accepts optional filter parameters that match the sidebar
widgets in app.py. Filters are applied as WHERE clauses so PostgreSQL
does the aggregation work — the dashboard never loads the full dataset
into memory.

Filter parameters (all optional, None = no filter applied):
    years   : list[int]  — e.g. [2023]
    severity: list[str]  — e.g. ['Fatal', 'Serious']
    road_types: list[str]
    weather_conditions: list[str]
    weekdays: list[int]  — 0=Monday ... 6=Sunday
    hours:    list[int]  — 0-23
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from dashboard.database import query_df, query_scalar


# ── Filter builder ─────────────────────────────────────────────────────────────

def _build_where(
    years=None, severity=None, road_types=None,
    weather_conditions=None, weekdays=None, hours=None,
) -> tuple:
    """
    Build a WHERE clause string and params tuple from active filters.

    Returns (where_clause_str, params_tuple).
    where_clause_str is empty string if no filters are active.
    """
    clauses = []
    params  = []

    if years:
        clauses.append(f"year = ANY(%s)")
        params.append(years)

    if severity:
        clauses.append("severity_label = ANY(%s)")
        params.append(severity)

    if road_types:
        clauses.append("road_type_name = ANY(%s)")
        params.append(road_types)

    if weather_conditions:
        clauses.append("weather_description = ANY(%s)")
        params.append(weather_conditions)

    if weekdays is not None and len(weekdays) > 0:
        clauses.append("weekday = ANY(%s)")
        params.append(weekdays)

    if hours is not None and len(hours) > 0:
        clauses.append("accident_hour = ANY(%s)")
        params.append(hours)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where, tuple(params)


# ── VIEW 1: KPI Summary ────────────────────────────────────────────────────────

def get_kpi_summary(years=None, severity=None, road_types=None,
                    weather_conditions=None) -> dict:
    """
    Returns a dict with:
      total_accidents, fatal_count, serious_count, slight_count,
      total_casualties, avg_vehicles, weather_matched_pct
    """
    where, params = _build_where(
        years=years, severity=severity,
        road_types=road_types, weather_conditions=weather_conditions
    )

    sql = f"""
        SELECT
            COUNT(*)                                                  AS total_accidents,
            SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
            SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count,
            SUM(CASE WHEN severity_label = 'Slight'  THEN 1 ELSE 0 END) AS slight_count,
            SUM(number_of_casualties)                                 AS total_casualties,
            ROUND(AVG(number_of_vehicles)::NUMERIC, 2)                AS avg_vehicles,
            ROUND(
                100.0 * SUM(CASE WHEN weather_matched THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                1
            )                                                         AS weather_matched_pct
        FROM accident_analytics_mart
        {where};
    """
    df = query_df(sql, params=params if params else None)
    if df.empty:
        return {k: 0 for k in [
            "total_accidents", "fatal_count", "serious_count", "slight_count",
            "total_casualties", "avg_vehicles", "weather_matched_pct"
        ]}
    row = df.iloc[0]
    return {
        "total_accidents":     int(row.get("total_accidents",  0) or 0),
        "fatal_count":         int(row.get("fatal_count",      0) or 0),
        "serious_count":       int(row.get("serious_count",    0) or 0),
        "slight_count":        int(row.get("slight_count",     0) or 0),
        "total_casualties":    int(row.get("total_casualties",  0) or 0),
        "avg_vehicles":        float(row.get("avg_vehicles",   0) or 0),
        "weather_matched_pct": float(row.get("weather_matched_pct", 0) or 0),
    }


# ── VIEW 2: Severity Distribution ─────────────────────────────────────────────

def get_severity_distribution(years=None, road_types=None,
                               weather_conditions=None) -> pd.DataFrame:
    """Returns accident_count by severity_label, ordered Fatal→Serious→Slight."""
    where, params = _build_where(
        years=years, road_types=road_types, weather_conditions=weather_conditions
    )
    sql = f"""
        SELECT
            severity_code,
            severity_label,
            COUNT(*) AS accident_count,
            SUM(number_of_casualties) AS total_casualties
        FROM accident_analytics_mart
        {where}
        GROUP BY severity_code, severity_label
        ORDER BY severity_code;
    """
    return query_df(sql, params=params if params else None)


# ── VIEW 3: Accidents by Hour ──────────────────────────────────────────────────

def get_accidents_by_hour(years=None, severity=None, road_types=None) -> pd.DataFrame:
    """Returns accident_count per hour of day (0-23)."""
    where, params = _build_where(
        years=years, severity=severity, road_types=road_types
    )
    sql = f"""
        SELECT
            accident_hour,
            COUNT(*) AS accident_count,
            SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
            SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count,
            SUM(CASE WHEN severity_label = 'Slight'  THEN 1 ELSE 0 END) AS slight_count
        FROM accident_analytics_mart
        {where}
        AND accident_hour IS NOT NULL
        GROUP BY accident_hour
        ORDER BY accident_hour;
    """
    # Fix: AND needs to be inside the WHERE block
    where2, params2 = _build_where(
        years=years, severity=severity, road_types=road_types
    )
    if where2:
        sql2 = f"""
            SELECT accident_hour,
                COUNT(*) AS accident_count,
                SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
                SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count,
                SUM(CASE WHEN severity_label = 'Slight'  THEN 1 ELSE 0 END) AS slight_count
            FROM accident_analytics_mart
            {where2} AND accident_hour IS NOT NULL
            GROUP BY accident_hour ORDER BY accident_hour;
        """
    else:
        sql2 = """
            SELECT accident_hour,
                COUNT(*) AS accident_count,
                SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
                SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count,
                SUM(CASE WHEN severity_label = 'Slight'  THEN 1 ELSE 0 END) AS slight_count
            FROM accident_analytics_mart
            WHERE accident_hour IS NOT NULL
            GROUP BY accident_hour ORDER BY accident_hour;
        """
    return query_df(sql2, params=params2 if params2 else None)


# ── VIEW 4: Accidents by Weekday ───────────────────────────────────────────────

def get_accidents_by_weekday(years=None, severity=None) -> pd.DataFrame:
    """Returns accident_count per weekday (0=Monday ... 6=Sunday)."""
    where, params = _build_where(years=years, severity=severity)
    null_filter = "AND weekday IS NOT NULL"
    if where:
        sql = f"""
            SELECT weekday, weekday_name, COUNT(*) AS accident_count,
                SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
                SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count
            FROM accident_analytics_mart
            {where} {null_filter}
            GROUP BY weekday, weekday_name ORDER BY weekday;
        """
    else:
        sql = f"""
            SELECT weekday, weekday_name, COUNT(*) AS accident_count,
                SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
                SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count
            FROM accident_analytics_mart
            WHERE weekday IS NOT NULL
            GROUP BY weekday, weekday_name ORDER BY weekday;
        """
    return query_df(sql, params=params if params else None)


# ── VIEW 5: Weather vs Severity ────────────────────────────────────────────────

def get_weather_vs_severity(years=None, road_types=None) -> pd.DataFrame:
    """
    Returns a cross-tab of accident counts by (weather_description, severity_label).
    Used for the stacked bar / heatmap chart.
    """
    where, params = _build_where(years=years, road_types=road_types)
    null_filter = "AND weather_description IS NOT NULL AND severity_label IS NOT NULL"
    if where:
        sql = f"""
            SELECT weather_description, severity_label, COUNT(*) AS accident_count
            FROM accident_analytics_mart
            {where} {null_filter}
            GROUP BY weather_description, severity_label
            ORDER BY accident_count DESC;
        """
    else:
        sql = f"""
            SELECT weather_description, severity_label, COUNT(*) AS accident_count
            FROM accident_analytics_mart
            WHERE weather_description IS NOT NULL AND severity_label IS NOT NULL
            GROUP BY weather_description, severity_label
            ORDER BY accident_count DESC;
        """
    return query_df(sql, params=params if params else None)


# ── VIEW 6: Accident Hotspot Map ───────────────────────────────────────────────

def get_hotspot_map_data(years=None, severity=None, limit: int = 5000) -> pd.DataFrame:
    """
    Returns individual accident lat/lon points for the map view.
    Limited to *limit* rows to keep the map responsive.
    Filtered by severity and year if provided.
    """
    where, params = _build_where(years=years, severity=severity)
    null_filter = "AND latitude IS NOT NULL AND longitude IS NOT NULL"

    if where:
        sql = f"""
            SELECT latitude, longitude, severity_label,
                   accident_date, accident_hour, number_of_casualties,
                   road_type_name, weather_description
            FROM accident_analytics_mart
            {where} {null_filter}
            LIMIT {int(limit)};
        """
    else:
        sql = f"""
            SELECT latitude, longitude, severity_label,
                   accident_date, accident_hour, number_of_casualties,
                   road_type_name, weather_description
            FROM accident_analytics_mart
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            LIMIT {int(limit)};
        """
    return query_df(sql, params=params if params else None)


# ── VIEW 7: Road Type vs Severity ──────────────────────────────────────────────

def get_road_type_vs_severity(years=None, severity=None) -> pd.DataFrame:
    """Returns accident counts broken down by road_type_name and severity_label."""
    where, params = _build_where(years=years, severity=severity)
    null_filter = "AND road_type_name IS NOT NULL AND severity_label IS NOT NULL"
    if where:
        sql = f"""
            SELECT road_type_name, severity_label,
                   COUNT(*) AS accident_count,
                   ROUND(AVG(speed_limit)::NUMERIC, 1) AS avg_speed_limit
            FROM accident_analytics_mart
            {where} {null_filter}
            GROUP BY road_type_name, severity_label
            ORDER BY accident_count DESC;
        """
    else:
        sql = f"""
            SELECT road_type_name, severity_label,
                   COUNT(*) AS accident_count,
                   ROUND(AVG(speed_limit)::NUMERIC, 1) AS avg_speed_limit
            FROM accident_analytics_mart
            WHERE road_type_name IS NOT NULL AND severity_label IS NOT NULL
            GROUP BY road_type_name, severity_label
            ORDER BY accident_count DESC;
        """
    return query_df(sql, params=params if params else None)


# ── VIEW 8: Vehicle & Casualty Analysis ───────────────────────────────────────

def get_vehicle_casualty_analysis(years=None, severity=None) -> pd.DataFrame:
    """
    Returns aggregated vehicle count vs casualty count grouped by
    number_of_vehicles to show the relationship between vehicle involvement
    and casualty outcomes.
    """
    where, params = _build_where(years=years, severity=severity)
    null_filter = "AND number_of_vehicles IS NOT NULL AND number_of_casualties IS NOT NULL"
    if where:
        sql = f"""
            SELECT number_of_vehicles,
                   COUNT(*) AS accident_count,
                   SUM(number_of_casualties)            AS total_casualties,
                   ROUND(AVG(number_of_casualties)::NUMERIC, 2) AS avg_casualties,
                   SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
                   SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count
            FROM accident_analytics_mart
            {where} {null_filter}
            GROUP BY number_of_vehicles
            ORDER BY number_of_vehicles;
        """
    else:
        sql = f"""
            SELECT number_of_vehicles,
                   COUNT(*) AS accident_count,
                   SUM(number_of_casualties)            AS total_casualties,
                   ROUND(AVG(number_of_casualties)::NUMERIC, 2) AS avg_casualties,
                   SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
                   SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count
            FROM accident_analytics_mart
            WHERE number_of_vehicles IS NOT NULL AND number_of_casualties IS NOT NULL
            GROUP BY number_of_vehicles
            ORDER BY number_of_vehicles;
        """
    return query_df(sql, params=params if params else None)


# ── Filter option loaders ──────────────────────────────────────────────────────

def get_filter_options() -> dict:
    """Load all distinct values for sidebar filter widgets."""
    opts = {}

    df_sev = query_df(
        "SELECT DISTINCT severity_label FROM accident_analytics_mart "
        "WHERE severity_label IS NOT NULL ORDER BY severity_label;"
    )
    opts["severity"] = df_sev["severity_label"].tolist() if not df_sev.empty else []

    df_road = query_df(
        "SELECT DISTINCT road_type_name FROM accident_analytics_mart "
        "WHERE road_type_name IS NOT NULL ORDER BY road_type_name;"
    )
    opts["road_types"] = df_road["road_type_name"].tolist() if not df_road.empty else []

    df_wx = query_df(
        "SELECT DISTINCT weather_description FROM accident_analytics_mart "
        "WHERE weather_description IS NOT NULL ORDER BY weather_description;"
    )
    opts["weather_conditions"] = df_wx["weather_description"].tolist() if not df_wx.empty else []

    df_yr = query_df(
        "SELECT DISTINCT year FROM accident_analytics_mart "
        "WHERE year IS NOT NULL ORDER BY year;"
    )
    opts["years"] = df_yr["year"].tolist() if not df_yr.empty else []

    return opts


def get_pipeline_log() -> pd.DataFrame:
    """Fetch the most recent 20 ingestion log entries for the sidebar info panel."""
    return query_df(
        """SELECT source_name, status, row_count, extraction_timestamp, error_message
           FROM ingestion_log
           ORDER BY extraction_timestamp DESC
           LIMIT 20;"""
    )
