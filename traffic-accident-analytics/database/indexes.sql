-- ============================================================
-- database/indexes.sql
-- Performance indexes for the Traffic Accident Analytics schema.
--
-- Run AFTER tables.sql and AFTER data is loaded.
-- Creating indexes on empty tables is fast but they are most
-- useful once data is present.
--
-- Usage:
--   psql -U postgres -d traffic_accidents -f database/indexes.sql
--
-- Design rationale
-- ────────────────
-- Indexes are chosen based on the dashboard query patterns:
--   - Filter by year / month / weekday  → dim_date columns
--   - Filter by severity                → severity_code / severity_label
--   - Filter by road type               → road_type_code / road_type_name
--   - Filter by weather                 → weather_description / weather_code
--   - Map view                          → latitude / longitude
--   - Aggregation by hour               → accident_hour
--
-- We do NOT create excessive indexes. Every index below has a
-- specific query in queries.py or the dashboard that uses it.
-- ============================================================

-- ── ingestion_log ─────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_ingestion_log_timestamp
    ON ingestion_log (extraction_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_ingestion_log_source
    ON ingestion_log (source_name, status);


-- ── dim_date ──────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_dim_date_year
    ON dim_date (year);

CREATE INDEX IF NOT EXISTS idx_dim_date_month
    ON dim_date (year, month);

CREATE INDEX IF NOT EXISTS idx_dim_date_weekday
    ON dim_date (weekday);


-- ── dim_location ──────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_dim_location_coords
    ON dim_location (latitude, longitude);


-- ── dim_road ──────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_dim_road_type_code
    ON dim_road (road_type_code);


-- ── fact_accident ─────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_fact_accident_index
    ON fact_accident (accident_index);

CREATE INDEX IF NOT EXISTS idx_fact_date
    ON fact_accident (date_id);

CREATE INDEX IF NOT EXISTS idx_fact_severity
    ON fact_accident (severity_id);

CREATE INDEX IF NOT EXISTS idx_fact_location
    ON fact_accident (location_id);

CREATE INDEX IF NOT EXISTS idx_fact_road
    ON fact_accident (road_id);

CREATE INDEX IF NOT EXISTS idx_fact_weather
    ON fact_accident (weather_id);

CREATE INDEX IF NOT EXISTS idx_fact_hour
    ON fact_accident (accident_hour);


-- ── accident_analytics_mart ───────────────────────────────────
-- These are the most important indexes — the dashboard reads
-- directly from this table, filtered by these columns.

CREATE INDEX IF NOT EXISTS idx_mart_accident_index
    ON accident_analytics_mart (accident_index);

CREATE INDEX IF NOT EXISTS idx_mart_date
    ON accident_analytics_mart (accident_date);

CREATE INDEX IF NOT EXISTS idx_mart_year
    ON accident_analytics_mart (year);

CREATE INDEX IF NOT EXISTS idx_mart_year_month
    ON accident_analytics_mart (year, month);

CREATE INDEX IF NOT EXISTS idx_mart_weekday
    ON accident_analytics_mart (weekday);

CREATE INDEX IF NOT EXISTS idx_mart_hour
    ON accident_analytics_mart (accident_hour);

CREATE INDEX IF NOT EXISTS idx_mart_severity_label
    ON accident_analytics_mart (severity_label);

CREATE INDEX IF NOT EXISTS idx_mart_severity_code
    ON accident_analytics_mart (severity_code);

CREATE INDEX IF NOT EXISTS idx_mart_road_type
    ON accident_analytics_mart (road_type_name);

CREATE INDEX IF NOT EXISTS idx_mart_weather_desc
    ON accident_analytics_mart (weather_description);

-- Composite index: supports the most common dashboard filter combo
-- (year + severity) used by the KPI cards
CREATE INDEX IF NOT EXISTS idx_mart_year_severity
    ON accident_analytics_mart (year, severity_label);

-- Composite index for map queries: year + coordinates
CREATE INDEX IF NOT EXISTS idx_mart_coords
    ON accident_analytics_mart (latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;


-- ── rejected_records ─────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_rejected_source
    ON rejected_records (source, rejected_at DESC);

CREATE INDEX IF NOT EXISTS idx_rejected_reason
    ON rejected_records (rejection_reason);


-- ── Verify indexes created ────────────────────────────────────
-- Run this to confirm:
--
-- SELECT schemaname, tablename, indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename IN (
--     'ingestion_log', 'dim_date', 'dim_location', 'dim_road',
--     'dim_severity', 'dim_weather', 'fact_accident',
--     'accident_analytics_mart', 'rejected_records'
-- )
-- ORDER BY tablename, indexname;
