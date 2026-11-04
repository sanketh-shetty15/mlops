# Traffic Accident Severity Analytics — Part 1

An end-to-end data engineering and analytics pipeline using UK road
safety data (STATS19) enriched with Open-Meteo weather observations,
stored in PostgreSQL, and visualised in a Streamlit dashboard.

---

## 1. Project Overview

This project builds a complete automated data pipeline that:

1. Downloads UK STATS19 accident, vehicle, and casualty data
2. Fetches historical hourly weather from the Open-Meteo API
3. Passes data through RAW → STAGING → CLEANED layers
4. Validates data quality using 18 named rules
5. Joins accident records with nearest-hour weather observations
6. Loads a star-schema PostgreSQL database
7. Builds a denormalised analytical data mart
8. Presents 8 interactive dashboard views in Streamlit

---

## 2. Problem Statement

Road traffic accidents are a leading cause of injury and death in the
UK. Understanding when, where, and under what conditions accidents occur
— and how severe they tend to be — is essential for road safety policy.
This project builds the data infrastructure needed to answer those
questions reproducibly and at scale.

---

## 3. Architecture

```
STATS19 (DfT) + Open-Meteo API
         ↓
    RAW DATA LAYER
         ↓
  AIRFLOW ETL PIPELINE
         ↓
    STAGING LAYER
         ↓
 DATA QUALITY VALIDATION
    ↙           ↘
VALID         REJECTED
  ↓
CLEANED DATA
  ↓
ACCIDENT + WEATHER JOIN
  ↓
POSTGRESQL (star schema)
  ↓
ANALYTICAL DATA MART
  ↓
STREAMLIT DASHBOARD
```

See `docs/architecture.md` for the full detailed diagram.

---

## 4. Technology Stack

| Technology | Version | Role |
|------------|---------|------|
| Python | 3.9+ | Pipeline language |
| Pandas | 2.1 | Data transformation |
| Requests | 2.31 | HTTP downloads |
| Apache Airflow | 2.8 | Pipeline orchestration |
| PostgreSQL | 14+ | Analytical database |
| psycopg2 | 2.9 | PostgreSQL driver |
| Streamlit | 1.29 | Dashboard |
| Plotly | 5.18 | Charts |
| pytest | 7.4 | Testing |
| python-dotenv | 1.0 | Environment configuration |

---

## 5. Dataset Sources

### UK Road Safety Open Data (STATS19)
- Publisher: Department for Transport (DfT)
- URL: https://www.gov.uk/government/statistical-data-sets/road-safety-open-data
- Licence: Open Government Licence v3.0
- Files used: Collisions, Vehicles, Casualties (2023)

### Open-Meteo Historical Weather API
- URL: https://open-meteo.com/en/docs/historical-weather-api
- Free, no API key required
- Provides hourly: temperature, precipitation, wind speed, weather code

See `docs/dataset_sources.md` for full details.

---

## 6. Dataset Download Instructions

The pipeline will attempt to download STATS19 CSVs automatically. If
automatic download fails (e.g. due to DfT server changes), download
manually:

1. Go to: https://www.gov.uk/government/statistical-data-sets/road-safety-open-data
2. Under **2023**, download the three files.
3. Place them here:

```
data/raw/accidents/dft-road-casualty-statistics-collision-2023.csv
data/raw/vehicles/dft-road-casualty-statistics-vehicle-2023.csv
data/raw/casualties/dft-road-casualty-statistics-casualty-2023.csv
```

Weather data is fetched automatically from Open-Meteo and cached in
`data/raw/weather/` as Parquet files. No manual download needed.

---

## 7. Project Structure

```
traffic-accident-analytics/
│
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── config/
│   └── config.py                  ← Central configuration (reads .env)
│
├── data/
│   ├── raw/
│   │   ├── accidents/             ← STATS19 collision CSV
│   │   ├── vehicles/              ← STATS19 vehicle CSV
│   │   ├── casualties/            ← STATS19 casualty CSV
│   │   └── weather/               ← Open-Meteo Parquet cache
│   ├── staging/                   ← Normalised, not yet cleaned
│   ├── cleaned/                   ← Validated, quality-checked
│   └── rejected/                  ← Failed quality checks + reports
│
├── ingestion/
│   ├── accident_ingestion.py      ← Download/load accident CSV
│   ├── vehicle_ingestion.py       ← Download/load vehicle CSV
│   ├── casualty_ingestion.py      ← Download/load casualty CSV
│   └── weather_ingestion.py       ← Fetch Open-Meteo (grid-snapped)
│
├── transformation/
│   ├── clean_accidents.py         ← Stage + clean accidents
│   ├── clean_vehicles.py          ← Stage + clean vehicles
│   ├── clean_casualties.py        ← Stage + clean casualties
│   ├── clean_weather.py           ← Clean weather Parquet files
│   ├── join_accident_weather.py   ← Left-join accidents + weather
│   └── create_analytics_mart.py   ← Build star schema + mart
│
├── validation/
│   ├── validation_rules.py        ← 18 named quality rules
│   └── data_quality.py            ← Run checks, print report
│
├── airflow/
│   └── dags/
│       └── traffic_accident_pipeline.py  ← Airflow DAG (15 tasks)
│
├── database/
│   ├── schema.sql                 ← Database + ingestion_log
│   ├── tables.sql                 ← All tables + views
│   └── indexes.sql                ← Performance indexes
│
├── dashboard/
│   ├── app.py                     ← Streamlit main application
│   ├── database.py                ← PostgreSQL connection helper
│   ├── queries.py                 ← All SQL queries with filters
│   └── charts.py                  ← Plotly chart builders
│
├── docs/
│   ├── architecture.md            ← Architecture diagram
│   ├── data_dictionary.md         ← All column definitions
│   ├── validation_rules.md        ← All 18 quality rules explained
│   └── dataset_sources.md         ← Source URLs and field lists
│
├── tests/
│   ├── test_ingestion.py          ← Grid snap, metadata tests
│   ├── test_validation.py         ← All 18 rule pass/fail tests
│   └── test_transformations.py    ← Staging, cleaning, join tests
│
└── scripts/
    ├── run_pipeline.py            ← Local pipeline runner (no Airflow)
    └── verify_database.py         ← Database health check
```

---

## 8. Environment Setup

### Step 1 — Clone and enter the project

```bash
cd "C:\Users\Sanketh H R\Projects\MLops\traffic-accident-analytics"
```

### Step 2 — Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

> **Note on Airflow (Windows):** Apache Airflow does not support Windows
> natively. Options:
> - Use Windows Subsystem for Linux (WSL2) — recommended
> - Use Docker Desktop with a Linux container
> - Skip Airflow and use `scripts/run_pipeline.py` directly (fully supported on Windows)

### Step 4 — Configure environment variables

```bash
copy .env.example .env
```

Edit `.env` with your PostgreSQL credentials:

```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=traffic_accidents
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
DATA_YEAR=2023
```

---

## 9. PostgreSQL Setup

### Option A — Neon (recommended, no local install needed)

[Neon](https://neon.tech) is a free serverless PostgreSQL cloud service.

1. Sign up at https://neon.tech (free tier is sufficient)
2. Create a new project — Neon creates a database for you automatically
3. In the Neon console, go to **Connection Details** and copy the **Connection string**. It looks like:
   ```
   postgresql://username:password@ep-xxx-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. Add it to your `.env` file:
   ```
   DATABASE_URL=postgresql://username:password@ep-xxx-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
5. The pipeline applies the SQL schema automatically on first run. Or apply it manually in the **Neon SQL Editor** (Dashboard → SQL Editor → paste contents of `database/schema.sql`, `database/tables.sql`, `database/indexes.sql`).

That's it — no local PostgreSQL installation needed.

### Option B — Local PostgreSQL

1. Install PostgreSQL 14+ from https://www.postgresql.org/download/windows/
2. Create the database:
   ```sql
   CREATE DATABASE traffic_accidents;
   ```
3. Set individual fields in `.env`:
   ```
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=traffic_accidents
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=your_password
   POSTGRES_SSLMODE=disable
   ```
4. Apply the schema:
   ```bash
   psql -U postgres -d traffic_accidents -f database/schema.sql
   psql -U postgres -d traffic_accidents -f database/tables.sql
   psql -U postgres -d traffic_accidents -f database/indexes.sql
   ```

### Option C — Docker PostgreSQL

```bash
docker run --name traffic-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=traffic_accidents -p 5432:5432 -d postgres:15
```
Then in `.env`:
```
POSTGRES_HOST=localhost
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=traffic_accidents
POSTGRES_SSLMODE=disable
```

---

## 10. Airflow Setup (Linux / WSL2 only)

```bash
# In WSL2 or Linux terminal
export AIRFLOW_HOME=$(pwd)/airflow
pip install apache-airflow==2.8.1

# Initialise the database
airflow db init

# Create an admin user
airflow users create \
    --username admin \
    --password admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com

# Point Airflow at the DAGs folder
export AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/airflow/dags

# Start the web server (in one terminal)
airflow webserver --port 8080

# Start the scheduler (in another terminal)
airflow scheduler
```

Open http://localhost:8080, log in with admin/admin, find the DAG
`traffic_accident_pipeline`, and click the **Trigger** button.

---

## 11. Running the Pipeline

### Option A — Without Airflow (recommended for development/Windows)

```bash
# Full pipeline
python scripts/run_pipeline.py

# Skip PostgreSQL (test CSV transforms only)
python scripts/run_pipeline.py --skip-db

# Force re-download of raw data
python scripts/run_pipeline.py --force-download

# Skip weather API (use cached Parquet files)
python scripts/run_pipeline.py --skip-weather-api

# Start from cleaning (raw + staging files already exist)
python scripts/run_pipeline.py --start-from cleaning
```

### Option B — With Airflow

```bash
# Trigger via CLI
airflow dags trigger traffic_accident_pipeline

# Or use the Airflow web UI at http://localhost:8080
```

### Pipeline stages and expected output

```
=====================================
  TRAFFIC ACCIDENT ANALYTICS PIPELINE
=====================================
▶  Starting: Extract accidents
✓  Completed: Extract accidents (8.3s)
▶  Starting: Extract vehicles
✓  Completed: Extract vehicles (9.1s)
...
▶  Starting: Run quality checks
✓  Completed: Run quality checks (2.1s)
=====================================
  PIPELINE COMPLETE in 142.7s
  Next step: streamlit run dashboard/app.py
=====================================
```

---

## 12. Running Streamlit

```bash
streamlit run dashboard/app.py
```

Then open: http://localhost:8501

The dashboard requires PostgreSQL to be running and the pipeline to have
completed at least once. If the database is empty, the dashboard will
show a helpful error message with instructions.

---

## 13. Running Tests

```bash
# All tests
pytest tests/ -v

# One file at a time
pytest tests/test_validation.py -v
pytest tests/test_transformations.py -v
pytest tests/test_ingestion.py -v

# With coverage
pytest tests/ --cov=. --cov-report=term-missing
```

Tests use in-memory DataFrames and do **not** require PostgreSQL or
internet access.

---

## 14. Verifying the Database

After the pipeline runs:

```bash
python scripts/verify_database.py

# Detailed output including indexes
python scripts/verify_database.py --verbose

# Save report to file
python scripts/verify_database.py --output db_report.txt
```

Expected output:

```
=================================================================
  DATABASE VERIFICATION REPORT
  Generated: 2024-01-15 14:30:00 UTC
=================================================================
  ✓ Connected to PostgreSQL successfully

  TABLE ROW COUNTS
  -----------------------------------------------------------------
  ingestion_log                           8  ✓
  dim_severity                            3  ✓
  dim_date                              365  ✓
  dim_location                       85,230  ✓
  dim_road                                7  ✓
  dim_weather                            20  ✓
  fact_accident                     100,245  ✓
  rejected_records                      127  ✓
  accident_analytics_mart           100,245  ✓
=================================================================
  ✓ DATABASE VERIFICATION: PASSED
  100,245 records in accident_analytics_mart — ready for dashboard
=================================================================
```

---

## 15. Data Quality Checks

The pipeline runs 18 validation rules across 4 datasets:

| Rule | Dataset | Action on Failure |
|------|---------|-------------------|
| accident_row_count | accidents | FAIL_PIPELINE |
| accident_id_not_null | accidents | REJECT |
| no_duplicate_accident_index | accidents | REJECT |
| latitude_range | accidents | REJECT |
| longitude_range | accidents | REJECT |
| accident_date_valid | accidents | REJECT |
| accident_time_format | accidents | LOG_WARN |
| severity_valid | accidents | REJECT |
| vehicle_count_positive | accidents | LOG_WARN |
| casualty_count_non_negative | accidents | REJECT |
| uk_bounding_box | accidents | LOG_WARN |
| vehicle_accident_index_not_null | vehicles | REJECT |
| vehicle_no_duplicates | vehicles | REJECT |
| casualty_accident_index_not_null | casualties | REJECT |
| casualty_severity_valid | casualties | REJECT |
| weather_row_count | weather | LOG_WARN |
| weather_datetime_not_null | weather | LOG_WARN |
| weather_temperature_plausible | weather | LOG_WARN |

Quality reports are saved to `data/rejected/quality_report_*.json`.

See `docs/validation_rules.md` for full rule definitions.

---

## 16. Database Schema

The database uses a **star schema**:

```
dim_date ─────────┐
dim_location ─────┤
dim_road ─────────┼──── fact_accident
dim_weather ──────┤
dim_severity ─────┘
```

The `accident_analytics_mart` is a wide denormalised table containing
all fields needed by the dashboard in one place, avoiding joins at
query time.

Six analytical SQL views are created automatically:
- `accidents_by_hour`
- `accidents_by_weekday`
- `accidents_by_severity`
- `accidents_by_weather`
- `accidents_by_road_type`
- `accident_hotspots`

See `docs/data_dictionary.md` for all column definitions.

---

## 17. Dashboard Views

| View | Chart Type | Answers |
|------|-----------|---------|
| KPI Summary | Metric cards | How many accidents? How many fatal/serious? |
| Severity Distribution | Donut + bar | What proportion are fatal vs slight? |
| Accidents by Hour | Stacked bar | When in the day do accidents peak? |
| Accidents by Weekday | Bar + line | Which days are most dangerous? |
| Weather vs Severity | Heatmap + bar | What weather is associated with serious accidents? |
| Hotspot Map | Scatter map | Where do accidents cluster? |
| Road Type vs Severity | Grouped bar | Which road types have more fatal accidents? |
| Vehicle & Casualty | Dual-axis | How do vehicle counts relate to casualties? |

All views update when the sidebar filters change (Year, Severity,
Road Type, Weather Condition).

---

## 18. Troubleshooting

### "Cannot connect to PostgreSQL"
- For Neon: check that `DATABASE_URL` is set correctly in `.env` and includes `?sslmode=require`
- For local: check PostgreSQL is running with `pg_isready -h localhost`
- Run: `python scripts/verify_database.py`
- Common Neon mistake: copying the **pooled** connection string (port 5432 on `ep-pooler-*`) vs the **direct** string — either works, but the direct string is simpler for this project

### "No accident CSV available"
- Download the STATS19 CSV manually (see Section 6)
- Place it in `data/raw/accidents/`

### "Weather data is empty"
- This is non-fatal — weather columns will be NULL
- Run `python ingestion/weather_ingestion.py` to retry
- Check internet connection

### "ImportError: No module named airflow"
- Airflow is not supported on Windows natively
- Use `python scripts/run_pipeline.py` instead
- Or set up WSL2 (see Section 10)

### "Dashboard shows no data"
- Run the pipeline first: `python scripts/run_pipeline.py`
- Verify the database: `python scripts/verify_database.py`
- Ensure `.env` credentials are correct

### Tests fail with import errors
- Activate the virtual environment: `venv\Scripts\activate`
- Install dependencies: `pip install -r requirements.txt`
- Run from project root: `pytest tests/ -v`

---

## 19. Idempotency

The pipeline is safe to re-run:
- Raw files are only re-downloaded with `--force-download`
- Weather API is only called for grid cells not yet cached
- PostgreSQL uses `TRUNCATE + INSERT ON CONFLICT DO NOTHING/UPDATE`
- Staging and cleaned CSV files are overwritten on each run
- Rejected records are appended with timestamps

---

## 20. Future Part 2 Extension

Part 2 will extend this project with:
- Severity prediction model (Random Forest / XGBoost / LightGBM)
- MLflow experiment tracking and model registry
- FastAPI model serving endpoint
- Docker deployment
- Model drift monitoring and retraining

The `accident_analytics_mart` table is already structured as a
model-ready dataset: all features are in one table with no joins
required for training.

---

## Data Attribution

- **UK STATS19:** Contains public sector information licensed under the
  [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
- **Weather data:** [Open-Meteo.com](https://open-meteo.com) — CC BY 4.0

---

## Quick Start (TL;DR)

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Configure — paste your Neon connection string
copy .env.example .env
# Edit .env and set:
#   DATABASE_URL=postgresql://user:pass@host/db?sslmode=require

# 3. Download STATS19 data → place in data/raw/accidents|vehicles|casualties/
#    (or let the pipeline attempt auto-download)

# 4. Run the full pipeline
python scripts/run_pipeline.py

# 5. Verify Neon DB
python scripts/verify_database.py

# 6. Launch dashboard
streamlit run dashboard/app.py
# Open http://localhost:8501

# 7. Run tests (no DB needed)
python -m pytest tests/ -v
```
