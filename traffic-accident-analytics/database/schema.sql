-- ============================================================
-- database/schema.sql
-- Creates the ingestion_log table and supporting schema.
--
-- ╔══════════════════════════════════════════════════════╗
-- ║  NEON USERS — READ THIS FIRST                        ║
-- ║                                                      ║
-- ║  Neon creates the database for you when you set up   ║
-- ║  your project. You do NOT need to run                ║
-- ║  CREATE DATABASE.                                    ║
-- ║                                                      ║
-- ║  Just run this file against your Neon database:      ║
-- ║                                                      ║
-- ║  Option A — Neon SQL Editor (easiest):               ║
-- ║    Paste the contents of this file into the          ║
-- ║    Neon console SQL Editor and click Run.            ║
-- ║                                                      ║
-- ║  Option B — psql with Neon connection string:        ║
-- ║    psql "postgresql://user:pass@host/db?sslmode=require" \
-- ║         -f database/schema.sql                       ║
-- ║                                                      ║
-- ║  The pipeline (run_pipeline.py) applies these SQL    ║
-- ║  files automatically on first run, so you can also   ║
-- ║  just run:  python scripts/run_pipeline.py           ║
-- ╚══════════════════════════════════════════════════════╝
--
-- LOCAL PostgreSQL users:
--   1. Create the database manually:
--      CREATE DATABASE traffic_accidents;
--   2. Then run this file:
--      psql -U postgres -d traffic_accidents -f database/schema.sql
-- ============================================================

-- ── Pipeline metadata schema ──────────────────────────────────────────────────
-- Records every extract/load operation for audit and debugging.

CREATE TABLE IF NOT EXISTS ingestion_log (
    id                   SERIAL       PRIMARY KEY,
    source_name          VARCHAR(100) NOT NULL,
    source_type          VARCHAR(50)  NOT NULL,   -- csv_download | api_open_meteo | data_quality_check
    extraction_timestamp TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status               VARCHAR(20)  NOT NULL,   -- SUCCESS | FAILED | WARN
    row_count            INTEGER,
    error_message        TEXT
);

COMMENT ON TABLE ingestion_log IS
    'Records every pipeline extraction/load operation. '
    'Used to track when data was collected, from where, '
    'and whether it succeeded.';
