# Architecture — Traffic Accident Severity Analytics

## Overview

This project implements an end-to-end data engineering and analytics pipeline
for UK road traffic accident data. It follows a layered architecture:
**Raw → Staging → Cleaned → Analytical**, with an Apache Airflow DAG
orchestrating each step and a Streamlit dashboard consuming the final output.

---

## Architecture Diagram

```
╔══════════════════════════════════════════════════════════════╗
║                     DATA SOURCES                             ║
║                                                              ║
║  ┌─────────────────────┐   ┌──────────────────────────────┐  ║
║  │  UK STATS19 (DfT)   │   │  Open-Meteo Historical API   │  ║
║  │  Collision CSV      │   │  Hourly weather by grid cell  │  ║
║  │  Vehicle CSV        │   │  Temperature, Precipitation,  │  ║
║  │  Casualty CSV       │   │  Wind, Cloud, Weather Code    │  ║
║  └──────────┬──────────┘   └──────────────┬───────────────┘  ║
╚═════════════╪═════════════════════════════╪════════════════╝
              │                             │
              ▼                             ▼
╔══════════════════════════════════════════════════════════════╗
║                    RAW DATA LAYER                            ║
║                                                              ║
║  data/raw/accidents/     ← STATS19 collision CSV (preserved) ║
║  data/raw/vehicles/      ← STATS19 vehicle CSV   (preserved) ║
║  data/raw/casualties/    ← STATS19 casualty CSV  (preserved) ║
║  data/raw/weather/       ← Open-Meteo Parquet cache files    ║
║                          (one file per 0.5° grid cell/year)  ║
╚══════════════════════════════════════╤═══════════════════════╝
                                       │
                                       ▼
╔══════════════════════════════════════════════════════════════╗
║            APACHE AIRFLOW DAG (traffic_accident_pipeline)    ║
║                                                              ║
║  extract_accidents ──┐                                       ║
║  extract_vehicles  ──┤──► validate_raw ──► create_staging    ║
║  extract_casualties──┤                                       ║
║  extract_weather   ──┘                                       ║
╚══════════════════════════════════════╤═══════════════════════╝
                                       │
                                       ▼
╔══════════════════════════════════════════════════════════════╗
║                    STAGING LAYER                             ║
║                                                              ║
║  data/staging/accidents_staged.csv                           ║
║  data/staging/vehicles_staged.csv                            ║
║  data/staging/casualties_staged.csv                          ║
║  data/staging/weather_staged.csv                             ║
║                                                              ║
║  Transformations applied:                                    ║
║  • Column names → snake_case                                 ║
║  • date: DD/MM/YYYY → datetime                               ║
║  • time: HH:MM → accident_hour (int)                         ║
║  • STATS19 -1 coded missing → NULL                           ║
║  • Numeric type casting                                      ║
╚══════════════════════════════════════╤═══════════════════════╝
                                       │
                                       ▼
╔══════════════════════════════════════════════════════════════╗
║                 DATA QUALITY VALIDATION                      ║
║                    (16 named rules)                          ║
╚══════════════════╤══════════════════════╤════════════════════╝
                   │                      │
                   ▼                      ▼
      ┌────────────────────┐   ┌──────────────────────────┐
      │   VALID RECORDS    │   │   REJECTED RECORDS        │
      │                    │   │                           │
      │ Pass all REJECT    │   │ data/rejected/            │
      │ rules              │   │ *_rejected.csv            │
      │                    │   │ quality_report_*.json     │
      └─────────┬──────────┘   └──────────────────────────┘
                │
                ▼
╔══════════════════════════════════════════════════════════════╗
║                    CLEANED DATA LAYER                        ║
║                                                              ║
║  data/cleaned/accidents_cleaned.csv                          ║
║  data/cleaned/vehicles_cleaned.csv                           ║
║  data/cleaned/casualties_cleaned.csv                         ║
║  data/cleaned/weather_cleaned.csv                            ║
╚══════════════════════════════════════╤═══════════════════════╝
                                       │
                                       ▼
╔══════════════════════════════════════════════════════════════╗
║              ACCIDENT + WEATHER JOIN                         ║
║                                                              ║
║  Strategy:                                                   ║
║  1. Snap accident lat/lon → 0.5° grid cell                   ║
║  2. Round accident time → nearest integer hour               ║
║  3. LEFT JOIN (accidents without weather → NULL weather cols) ║
║                                                              ║
║  Output: data/cleaned/accidents_with_weather.csv             ║
╚══════════════════════════════════════╤═══════════════════════╝
                                       │
                                       ▼
╔══════════════════════════════════════════════════════════════╗
║             POSTGRESQL / STAR SCHEMA                         ║
║                                                              ║
║  Dimensions:                                                 ║
║    dim_date       dim_location    dim_road                   ║
║    dim_severity   dim_weather                                ║
║                                                              ║
║  Fact:                                                       ║
║    fact_accident  (FK → all dims, measures: vehicle/casualty ║
║                   counts, weather values)                    ║
║                                                              ║
║  Rejected:                                                   ║
║    rejected_records  (source, reason, original JSON)         ║
║                                                              ║
║  Audit:                                                      ║
║    ingestion_log  (every pipeline run recorded)              ║
╚══════════════════════════════════════╤═══════════════════════╝
                                       │
                                       ▼
╔══════════════════════════════════════════════════════════════╗
║              ANALYTICAL DATA MART                            ║
║                                                              ║
║  accident_analytics_mart  (wide denormalised table)          ║
║                                                              ║
║  Analytical views:                                           ║
║    accidents_by_hour      accidents_by_weekday               ║
║    accidents_by_severity  accidents_by_weather               ║
║    accidents_by_road_type accident_hotspots                  ║
╚══════════════════════════════════════╤═══════════════════════╝
                                       │
                                       ▼
╔══════════════════════════════════════════════════════════════╗
║               STREAMLIT DASHBOARD                            ║
║                                                              ║
║  View 1: KPI Summary (total accidents, fatal, casualties)    ║
║  View 2: Severity Distribution (donut + bar)                 ║
║  View 3: Accidents by Hour (stacked bar)                     ║
║  View 4: Accidents by Weekday (bar + fatal line)             ║
║  View 5: Weather vs Severity (heatmap + stacked bar)         ║
║  View 6: Accident Hotspot Map (scatter map)                  ║
║  View 7: Road Type vs Severity (grouped bar)                 ║
║  View 8: Vehicle & Casualty Analysis (dual-axis)             ║
║                                                              ║
║  All charts respond to sidebar filters:                      ║
║    Year | Severity | Road Type | Weather Condition           ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Why Each Layer Exists

| Layer | Purpose |
|-------|---------|
| **Raw** | Preserve the original source data. The pipeline can be rebuilt from raw files without re-downloading. Never modified after ingestion. |
| **Staging** | Apply format normalisation (snake_case, date parsing, type casting). No records are removed at this stage. |
| **Cleaning** | Apply business rules to reject invalid records. Invalid rows are moved to `data/rejected/` with a documented reason. |
| **Validation** | Run 16 named quality rules. Produces a quality report. Separates `REJECT` (hard failure) from `LOG_WARN` (soft warning). |
| **Join** | Enrich each accident with the nearest-hour weather observation for its location. Uses a left join so no accidents are lost. |
| **PostgreSQL** | Provide a structured, queryable store. Star schema supports efficient analytical queries. |
| **Analytical Mart** | Denormalised wide table optimised for dashboard queries. Avoids joins at query time. |
| **Dashboard** | Presents 8 interactive views to analysts. All data comes from PostgreSQL — no manually edited files. |

---

## Why Airflow?

Airflow provides:
- **Task dependency tracking** — each step only runs when its dependencies succeed
- **Retries** — extraction tasks retry 3 times before failing
- **Observability** — every task run is logged with start/end time and status
- **Reproducibility** — the same DAG can be triggered again to rebuild the database
- **Manual control** — `schedule=None` prevents accidental re-runs that would re-hit the weather API

---

## Technology Choices

| Technology | Role | Why |
|------------|------|-----|
| Python | Pipeline language | Widespread, rich data ecosystem |
| Pandas | Data transformation | DataFrame operations, CSV I/O |
| Requests | HTTP downloads | STATS19 CSV + Open-Meteo API |
| Apache Airflow | Orchestration | DAG-based task scheduling |
| PostgreSQL | Analytical database | ACID, SQL, window functions |
| Streamlit | Dashboard | Pure Python, rapid development |
| Plotly | Charts | Interactive, professional quality |
| pytest | Testing | Standard Python test framework |
| python-dotenv | Configuration | No hardcoded credentials |

---

## Data Flow Summary

```
DfT gov.uk CSV  ─┐
                  ├─► RAW ─► STAGING ─► CLEANING ─┬─► VALID ─► JOIN ─► POSTGRESQL ─► MART ─► DASHBOARD
Open-Meteo API ──┘                                 └─► REJECTED ─► data/rejected/
```
