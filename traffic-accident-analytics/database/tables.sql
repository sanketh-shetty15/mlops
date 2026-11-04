-- ============================================================
-- database/tables.sql
-- Creates all dimension tables, fact table, analytical mart,
-- and supporting views for the Traffic Accident Analytics project.
--
-- Run AFTER schema.sql.
--
-- Usage:
--   psql -U postgres -d traffic_accidents -f database/tables.sql
--
-- Idempotency: all statements use CREATE TABLE IF NOT EXISTS.
-- Re-running will NOT drop existing data.
-- To reset: run DROP TABLE ... CASCADE before re-running.
-- ============================================================

-- ============================================================
-- DIMENSION TABLES
-- ============================================================

-- ── dim_severity ──────────────────────────────────────────────
-- Maps STATS19 numeric severity codes to human-readable labels.
-- Source: STATS19 data guide
--   1 = Fatal, 2 = Serious, 3 = Slight

CREATE TABLE IF NOT EXISTS dim_severity (
    severity_id    SMALLINT     PRIMARY KEY,   -- 1, 2, or 3
    severity_name  VARCHAR(20)  NOT NULL        -- 'Fatal', 'Serious', 'Slight'
);

COMMENT ON TABLE dim_severity IS
    'Lookup table mapping STATS19 accident severity codes to names. '
    'Values: 1=Fatal, 2=Serious, 3=Slight.';


-- ── dim_date ──────────────────────────────────────────────────
-- One row per unique accident date.
-- Enables time-based aggregations in the dashboard without
-- full date parsing on every query.

CREATE TABLE IF NOT EXISTS dim_date (
    date_id       SERIAL       PRIMARY KEY,
    full_date     DATE         NOT NULL UNIQUE,
    year          SMALLINT     NOT NULL,
    month         SMALLINT     NOT NULL,   -- 1-12
    month_name    VARCHAR(10)  NOT NULL,   -- 'January' ... 'December'
    day           SMALLINT     NOT NULL,   -- 1-31
    weekday       SMALLINT     NOT NULL,   -- 0=Monday ... 6=Sunday
    weekday_name  VARCHAR(10)  NOT NULL,   -- 'Monday' ... 'Sunday'
    quarter       SMALLINT     NOT NULL    -- 1-4
);

COMMENT ON TABLE dim_date IS
    'Date dimension derived from accident dates. '
    'Supports year/month/weekday slicing in dashboard queries.';


-- ── dim_location ──────────────────────────────────────────────
-- One row per unique (latitude, longitude) pair.
-- Stores the accident location for map visualisations.
-- If PostGIS is installed, the geom column provides a proper
-- geographic point for spatial queries.

CREATE TABLE IF NOT EXISTS dim_location (
    location_id          SERIAL   PRIMARY KEY,
    latitude             DOUBLE PRECISION NOT NULL,
    longitude            DOUBLE PRECISION NOT NULL,
    urban_rural_code     SMALLINT,   -- 1=Urban, 2=Rural (STATS19 code)
    local_authority_code INTEGER,    -- STATS19 local_authority_district code
    UNIQUE (latitude, longitude)
);

-- Optional PostGIS geography column.
-- Uncomment if PostGIS extension is installed.
-- ALTER TABLE dim_location
--     ADD COLUMN IF NOT EXISTS geom GEOGRAPHY(Point, 4326);
-- UPDATE dim_location SET geom = ST_MakePoint(longitude, latitude)
--     WHERE geom IS NULL;

COMMENT ON TABLE dim_location IS
    'Location dimension with lat/lon from STATS19. '
    'One row per unique coordinate pair. '
    'urban_rural_code: 1=Urban, 2=Rural.';


-- ── dim_road ──────────────────────────────────────────────────
-- One row per unique road-type configuration.
-- road_type_code maps to STATS19:
--   1=Roundabout, 2=One way, 3=Dual carriageway,
--   6=Single carriageway, 7=Slip road, 9=Unknown

CREATE TABLE IF NOT EXISTS dim_road (
    road_id            SERIAL      PRIMARY KEY,
    road_type_code     SMALLINT    NOT NULL UNIQUE,
    road_type_name     VARCHAR(50),
    speed_limit        SMALLINT,   -- mph, NULL if not available
    junction_detail    SMALLINT,   -- STATS19 junction_detail code
    junction_control   SMALLINT,   -- STATS19 junction_control code
    first_road_class   SMALLINT    -- STATS19 first_road_class code
);

COMMENT ON TABLE dim_road IS
    'Road type dimension derived from STATS19 road_type codes. '
    'speed_limit is in mph. junction_detail and junction_control '
    'retain STATS19 numeric codes.';


-- ── dim_weather ───────────────────────────────────────────────
-- One row per unique WMO weather code returned by Open-Meteo.
-- Codes 0-99, see config.py for full description map.

CREATE TABLE IF NOT EXISTS dim_weather (
    weather_id          SERIAL      PRIMARY KEY,
    weather_code        SMALLINT    NOT NULL UNIQUE,
    weather_description VARCHAR(80) NOT NULL
);

COMMENT ON TABLE dim_weather IS
    'Weather condition dimension from Open-Meteo WMO codes. '
    '0=Clear sky, 61=Slight rain, 95=Thunderstorm, etc.';


-- ============================================================
-- FACT TABLE
-- ============================================================

-- ── fact_accident ─────────────────────────────────────────────
-- Central fact table. One row per accident.
-- Foreign keys link to all dimension tables.
-- Measures: vehicle_count, casualty_count, speed_limit.
-- Weather columns are denormalised here as well as referenced
-- via weather_id to support fast dashboard queries.

CREATE TABLE IF NOT EXISTS fact_accident (
    accident_id              SERIAL        PRIMARY KEY,
    accident_index           VARCHAR(50)   NOT NULL UNIQUE,  -- STATS19 unique ID
    date_id                  INTEGER       REFERENCES dim_date(date_id),
    location_id              INTEGER       REFERENCES dim_location(location_id),
    road_id                  INTEGER       REFERENCES dim_road(road_id),
    weather_id               INTEGER       REFERENCES dim_weather(weather_id),
    severity_id              SMALLINT      REFERENCES dim_severity(severity_id),

    -- Measures from STATS19
    vehicle_count            SMALLINT,
    casualty_count           SMALLINT,
    accident_hour            SMALLINT,     -- 0-23
    speed_limit              SMALLINT,     -- mph
    light_conditions         SMALLINT,     -- STATS19 code
    road_surface_conditions  SMALLINT,     -- STATS19 code
    urban_rural_area         SMALLINT,     -- 1=Urban, 2=Rural

    -- Denormalised weather measures (NULL when weather not matched)
    temperature_2m           REAL,         -- °C
    precipitation            REAL,         -- mm
    wind_speed_10m           REAL,         -- mph
    weather_description      VARCHAR(80),

    -- Metadata
    loaded_at                TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE fact_accident IS
    'Central fact table. One row per STATS19 accident. '
    'Links to all dimensions via foreign keys. '
    'Weather columns are NULL when Open-Meteo data was not available '
    'for the accident location/time.';


-- ============================================================
-- REJECTED RECORDS TABLE
-- ============================================================
-- Stores records that failed data-quality validation.
-- Kept in the database for audit and re-processing.

CREATE TABLE IF NOT EXISTS rejected_records (
    rejected_id        SERIAL       PRIMARY KEY,
    source             VARCHAR(50)  NOT NULL,     -- 'accidents' | 'vehicles' | 'casualties'
    record_identifier  VARCHAR(100),              -- accident_index or similar
    rejection_reason   VARCHAR(200) NOT NULL,
    original_record    JSONB,                     -- the full original row as JSON
    rejected_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE rejected_records IS
    'Records removed during data-quality validation. '
    'original_record stores the full row as JSON for audit. '
    'rejection_reason explains why the record was rejected.';


-- ============================================================
-- ANALYTICAL MART
-- ============================================================
-- A single wide, denormalised table optimised for dashboard queries.
-- Updated by create_analytics_mart.py after every pipeline run.
-- All columns are derived from the STATS19 + Open-Meteo sources.

CREATE TABLE IF NOT EXISTS accident_analytics_mart (
    accident_index          VARCHAR(50)   PRIMARY KEY,

    -- Time
    accident_date           DATE,
    year                    SMALLINT,
    month                   SMALLINT,
    month_name              VARCHAR(10),
    weekday                 SMALLINT,     -- 0=Monday
    weekday_name            VARCHAR(10),
    accident_hour           SMALLINT,     -- 0-23

    -- Location
    latitude                DOUBLE PRECISION,
    longitude               DOUBLE PRECISION,

    -- Severity
    severity_code           SMALLINT,
    severity_label          VARCHAR(10),  -- 'Fatal' | 'Serious' | 'Slight'

    -- Road
    road_type_code          SMALLINT,
    road_type_name          VARCHAR(50),
    speed_limit             SMALLINT,
    junction_detail         SMALLINT,
    light_conditions        SMALLINT,
    road_surface_conditions SMALLINT,
    urban_rural_area        SMALLINT,

    -- Counts
    number_of_vehicles      SMALLINT,
    number_of_casualties    SMALLINT,

    -- Weather (NULL when not matched)
    temperature_2m          REAL,
    precipitation           REAL,
    wind_speed_10m          REAL,
    weather_code            SMALLINT,
    weather_description     VARCHAR(80),
    weather_matched         BOOLEAN       DEFAULT FALSE,

    -- Metadata
    loaded_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE accident_analytics_mart IS
    'Denormalised analytical table optimised for dashboard queries. '
    'One row per accident. Contains all fields needed for the '
    'Streamlit dashboard views without joins. '
    'weather_matched=FALSE means the accident had no weather data available.';


-- ============================================================
-- ANALYTICAL VIEWS
-- ============================================================
-- Pre-aggregated views for common dashboard queries.
-- Views are recomputed on-the-fly; no extra storage needed.

-- Accidents by hour of day
CREATE OR REPLACE VIEW accidents_by_hour AS
SELECT
    accident_hour,
    COUNT(*)                                           AS accident_count,
    SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
    SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count,
    SUM(CASE WHEN severity_label = 'Slight'  THEN 1 ELSE 0 END) AS slight_count
FROM accident_analytics_mart
WHERE accident_hour IS NOT NULL
GROUP BY accident_hour
ORDER BY accident_hour;

COMMENT ON VIEW accidents_by_hour IS
    'Aggregated accident counts by hour of day (0-23), split by severity.';


-- Accidents by weekday
CREATE OR REPLACE VIEW accidents_by_weekday AS
SELECT
    weekday,
    weekday_name,
    COUNT(*)                                           AS accident_count,
    SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
    SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count,
    SUM(CASE WHEN severity_label = 'Slight'  THEN 1 ELSE 0 END) AS slight_count
FROM accident_analytics_mart
WHERE weekday IS NOT NULL
GROUP BY weekday, weekday_name
ORDER BY weekday;

COMMENT ON VIEW accidents_by_weekday IS
    'Aggregated accident counts by day of week, split by severity.';


-- Accidents by severity
CREATE OR REPLACE VIEW accidents_by_severity AS
SELECT
    severity_code,
    severity_label,
    COUNT(*)                             AS accident_count,
    SUM(number_of_casualties)            AS total_casualties,
    ROUND(AVG(number_of_vehicles)::NUMERIC, 2) AS avg_vehicles
FROM accident_analytics_mart
WHERE severity_label IS NOT NULL
GROUP BY severity_code, severity_label
ORDER BY severity_code;

COMMENT ON VIEW accidents_by_severity IS
    'Accident counts, total casualties, and average vehicles by severity level.';


-- Accidents by weather condition
CREATE OR REPLACE VIEW accidents_by_weather AS
SELECT
    weather_code,
    weather_description,
    COUNT(*)                                           AS accident_count,
    SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
    SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count,
    SUM(CASE WHEN severity_label = 'Slight'  THEN 1 ELSE 0 END) AS slight_count,
    ROUND(AVG(number_of_casualties)::NUMERIC, 2)       AS avg_casualties
FROM accident_analytics_mart
WHERE weather_description IS NOT NULL
GROUP BY weather_code, weather_description
ORDER BY accident_count DESC;

COMMENT ON VIEW accidents_by_weather IS
    'Accident counts and severity breakdown by Open-Meteo weather condition.';


-- Accidents by road type
CREATE OR REPLACE VIEW accidents_by_road_type AS
SELECT
    road_type_code,
    road_type_name,
    COUNT(*)                                           AS accident_count,
    SUM(CASE WHEN severity_label = 'Fatal'   THEN 1 ELSE 0 END) AS fatal_count,
    SUM(CASE WHEN severity_label = 'Serious' THEN 1 ELSE 0 END) AS serious_count,
    SUM(CASE WHEN severity_label = 'Slight'  THEN 1 ELSE 0 END) AS slight_count,
    ROUND(AVG(speed_limit)::NUMERIC, 1)                AS avg_speed_limit
FROM accident_analytics_mart
WHERE road_type_name IS NOT NULL
GROUP BY road_type_code, road_type_name
ORDER BY accident_count DESC;

COMMENT ON VIEW accidents_by_road_type IS
    'Accident counts and severity breakdown by road type.';


-- Accident hotspots (top 500 locations by accident count)
CREATE OR REPLACE VIEW accident_hotspots AS
SELECT
    ROUND(latitude::NUMERIC,  4) AS latitude,
    ROUND(longitude::NUMERIC, 4) AS longitude,
    COUNT(*)                                            AS accident_count,
    SUM(CASE WHEN severity_label = 'Fatal'    THEN 1 ELSE 0 END) AS fatal_count,
    SUM(CASE WHEN severity_label = 'Serious'  THEN 1 ELSE 0 END) AS serious_count,
    SUM(number_of_casualties)                           AS total_casualties
FROM accident_analytics_mart
WHERE latitude IS NOT NULL AND longitude IS NOT NULL
GROUP BY ROUND(latitude::NUMERIC, 4), ROUND(longitude::NUMERIC, 4)
ORDER BY accident_count DESC
LIMIT 500;

COMMENT ON VIEW accident_hotspots IS
    'Top 500 coordinate locations by accident frequency. '
    'Used to power the hotspot map on the Streamlit dashboard.';
