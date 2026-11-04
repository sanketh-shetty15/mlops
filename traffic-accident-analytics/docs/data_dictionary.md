# Data Dictionary — Traffic Accident Severity Analytics

This document describes every column present in the final
`accident_analytics_mart` table and supporting dimension tables.
Only actual columns from the STATS19 source and Open-Meteo API are
documented. No invented columns are included.

---

## accident_analytics_mart

The primary analytical table. One row per accident. All fields needed
for dashboard queries are present without requiring joins.

| Column | Type | Description | Source | Nullable | Validation Rule | Example |
|--------|------|-------------|--------|----------|-----------------|---------|
| `accident_index` | VARCHAR(50) | Unique STATS19 collision identifier | STATS19 collision | No | Must not be NULL, must be unique | `2023010046872` |
| `accident_date` | DATE | Date of the accident | STATS19 `date` (parsed from DD/MM/YYYY) | No | Must be a valid date | `2023-03-15` |
| `year` | SMALLINT | Year derived from accident_date | Derived | No | Must be >= 1979 | `2023` |
| `month` | SMALLINT | Month number (1–12) | Derived | No | 1 ≤ month ≤ 12 | `3` |
| `month_name` | VARCHAR(10) | Month name | Derived | No | Valid month name | `March` |
| `weekday` | SMALLINT | Day of week (0=Monday, 6=Sunday) | Derived | No | 0 ≤ weekday ≤ 6 | `2` |
| `weekday_name` | VARCHAR(10) | Day name | Derived | No | Valid day name | `Wednesday` |
| `accident_hour` | SMALLINT | Hour of day (0–23) | STATS19 `time` (parsed HH:MM → hour) | Yes | 0 ≤ hour ≤ 23 | `8` |
| `latitude` | DOUBLE PRECISION | Accident latitude (WGS84) | STATS19 `latitude` | No | −90 ≤ lat ≤ 90 | `51.507` |
| `longitude` | DOUBLE PRECISION | Accident longitude (WGS84) | STATS19 `longitude` | No | −180 ≤ lon ≤ 180 | `−0.128` |
| `severity_code` | SMALLINT | STATS19 numeric severity code | STATS19 `accident_severity` | No | Must be 1, 2, or 3 | `2` |
| `severity_label` | VARCHAR(10) | Human-readable severity | Derived from severity_code | No | Fatal/Serious/Slight | `Serious` |
| `road_type_code` | SMALLINT | STATS19 road type code | STATS19 `road_type` | Yes | Valid STATS19 code | `6` |
| `road_type_name` | VARCHAR(50) | Road type description | Derived from road_type_code | Yes | Valid road type | `Single carriageway` |
| `speed_limit` | SMALLINT | Posted speed limit in mph | STATS19 `speed_limit` | Yes | Must be > 0 if present | `30` |
| `junction_detail` | SMALLINT | Junction type code | STATS19 `junction_detail` | Yes | STATS19 coded value | `3` |
| `light_conditions` | SMALLINT | Light conditions code | STATS19 `light_conditions` | Yes | STATS19 coded value | `1` |
| `road_surface_conditions` | SMALLINT | Road surface code | STATS19 `road_surface_conditions` | Yes | STATS19 coded value | `1` |
| `urban_rural_area` | SMALLINT | Urban/rural flag | STATS19 `urban_or_rural_area` | Yes | 1=Urban, 2=Rural | `1` |
| `number_of_vehicles` | SMALLINT | Vehicles involved in the accident | STATS19 `number_of_vehicles` | Yes | Must be ≥ 1 if present | `2` |
| `number_of_casualties` | SMALLINT | Casualties in the accident | STATS19 `number_of_casualties` | Yes | Must be ≥ 0 | `1` |
| `temperature_2m` | REAL | Air temperature at 2 m height (°C) | Open-Meteo `temperature_2m` | Yes | −30 ≤ temp ≤ 45 | `12.5` |
| `precipitation` | REAL | Total precipitation in mm | Open-Meteo `precipitation` | Yes | ≥ 0 | `0.0` |
| `wind_speed_10m` | REAL | Wind speed at 10 m height (mph) | Open-Meteo `wind_speed_10m` | Yes | ≥ 0 | `10.2` |
| `weather_code` | SMALLINT | WMO weather condition code | Open-Meteo `weather_code` | Yes | Valid WMO code | `2` |
| `weather_description` | VARCHAR(80) | Human-readable weather condition | Derived from weather_code | Yes | Valid description | `Partly cloudy` |
| `weather_matched` | BOOLEAN | True if weather data was found for this accident | Derived from join | No | TRUE/FALSE | `true` |
| `loaded_at` | TIMESTAMPTZ | When this row was loaded into PostgreSQL | Pipeline | No | Auto-set | `2024-01-15T14:30:00Z` |

---

## dim_severity

| Column | Type | Description | Source | Nullable | Example |
|--------|------|-------------|--------|----------|---------|
| `severity_id` | SMALLINT (PK) | STATS19 severity code | STATS19 | No | `1` |
| `severity_name` | VARCHAR(20) | Severity label | Derived | No | `Fatal` |

**Code mapping:** 1 = Fatal, 2 = Serious, 3 = Slight

---

## dim_date

| Column | Type | Description | Source | Nullable | Example |
|--------|------|-------------|--------|----------|---------|
| `date_id` | SERIAL (PK) | Surrogate key | Generated | No | `1` |
| `full_date` | DATE (UNIQUE) | The calendar date | Derived | No | `2023-03-15` |
| `year` | SMALLINT | Calendar year | Derived | No | `2023` |
| `month` | SMALLINT | Month number | Derived | No | `3` |
| `month_name` | VARCHAR(10) | Month name | Derived | No | `March` |
| `day` | SMALLINT | Day of month | Derived | No | `15` |
| `weekday` | SMALLINT | 0=Monday … 6=Sunday | Derived | No | `2` |
| `weekday_name` | VARCHAR(10) | Day name | Derived | No | `Wednesday` |
| `quarter` | SMALLINT | Quarter (1–4) | Derived | No | `1` |

---

## dim_location

| Column | Type | Description | Source | Nullable | Example |
|--------|------|-------------|--------|----------|---------|
| `location_id` | SERIAL (PK) | Surrogate key | Generated | No | `42` |
| `latitude` | DOUBLE PRECISION | WGS84 latitude | STATS19 | No | `51.507` |
| `longitude` | DOUBLE PRECISION | WGS84 longitude | STATS19 | No | `−0.128` |
| `urban_rural_code` | SMALLINT | 1=Urban, 2=Rural | STATS19 | Yes | `1` |
| `local_authority_code` | INTEGER | STATS19 local authority code | STATS19 | Yes | `501` |

---

## dim_road

| Column | Type | Description | Source | Nullable | Example |
|--------|------|-------------|--------|----------|---------|
| `road_id` | SERIAL (PK) | Surrogate key | Generated | No | `5` |
| `road_type_code` | SMALLINT (UNIQUE) | STATS19 road type code | STATS19 | No | `6` |
| `road_type_name` | VARCHAR(50) | Road type description | Derived | Yes | `Single carriageway` |
| `speed_limit` | SMALLINT | Speed limit in mph | STATS19 | Yes | `30` |
| `junction_detail` | SMALLINT | Junction type code | STATS19 | Yes | `3` |
| `junction_control` | SMALLINT | Junction control code | STATS19 | Yes | `4` |
| `first_road_class` | SMALLINT | Road class code | STATS19 | Yes | `3` |

**Road type codes:** 1=Roundabout, 2=One way street, 3=Dual carriageway,
6=Single carriageway, 7=Slip road, 9=Unknown

---

## dim_weather

| Column | Type | Description | Source | Nullable | Example |
|--------|------|-------------|--------|----------|---------|
| `weather_id` | SERIAL (PK) | Surrogate key | Generated | No | `3` |
| `weather_code` | SMALLINT (UNIQUE) | WMO condition code | Open-Meteo | No | `61` |
| `weather_description` | VARCHAR(80) | Condition description | Derived | No | `Slight rain` |

**Selected WMO codes:** 0=Clear sky, 2=Partly cloudy, 3=Overcast,
45=Fog, 61=Slight rain, 63=Moderate rain, 71=Slight snow, 95=Thunderstorm

---

## fact_accident

| Column | Type | Description | Nullable |
|--------|------|-------------|----------|
| `accident_id` | SERIAL (PK) | Surrogate key | No |
| `accident_index` | VARCHAR(50) (UNIQUE) | STATS19 unique ID | No |
| `date_id` | INTEGER (FK → dim_date) | Date foreign key | Yes |
| `location_id` | INTEGER (FK → dim_location) | Location foreign key | Yes |
| `road_id` | INTEGER (FK → dim_road) | Road foreign key | Yes |
| `weather_id` | INTEGER (FK → dim_weather) | Weather foreign key | Yes |
| `severity_id` | SMALLINT (FK → dim_severity) | Severity foreign key | Yes |
| `vehicle_count` | SMALLINT | Vehicles involved | Yes |
| `casualty_count` | SMALLINT | Casualties | Yes |
| `accident_hour` | SMALLINT | Hour of day (0–23) | Yes |
| `speed_limit` | SMALLINT | Speed limit mph | Yes |
| `light_conditions` | SMALLINT | STATS19 code | Yes |
| `road_surface_conditions` | SMALLINT | STATS19 code | Yes |
| `urban_rural_area` | SMALLINT | 1=Urban, 2=Rural | Yes |
| `temperature_2m` | REAL | °C at time of accident | Yes |
| `precipitation` | REAL | mm at time of accident | Yes |
| `wind_speed_10m` | REAL | mph at time of accident | Yes |
| `weather_description` | VARCHAR(80) | Denormalised for speed | Yes |
| `loaded_at` | TIMESTAMPTZ | Load timestamp | No |

---

## rejected_records

| Column | Type | Description | Nullable | Example |
|--------|------|-------------|----------|---------|
| `rejected_id` | SERIAL (PK) | Surrogate key | No | `1` |
| `source` | VARCHAR(50) | Source dataset | No | `accidents` |
| `record_identifier` | VARCHAR(100) | accident_index or similar | Yes | `2023010046872` |
| `rejection_reason` | VARCHAR(200) | Why the record was rejected | No | `invalid_latitude` |
| `original_record` | JSONB | Full original row as JSON | Yes | `{"accident_index": ...}` |
| `rejected_at` | TIMESTAMPTZ | When rejection occurred | No | `2024-01-15T14:30:00Z` |

---

## ingestion_log

| Column | Type | Description | Nullable | Example |
|--------|------|-------------|----------|---------|
| `id` | SERIAL (PK) | Surrogate key | No | `1` |
| `source_name` | VARCHAR(100) | Name of data source | No | `accidents_2023` |
| `source_type` | VARCHAR(50) | Type of extraction | No | `csv_download` |
| `extraction_timestamp` | TIMESTAMPTZ | When extraction occurred | No | `2024-01-15T14:00:00Z` |
| `status` | VARCHAR(20) | SUCCESS / FAILED / WARN | No | `SUCCESS` |
| `row_count` | INTEGER | Rows extracted | Yes | `100245` |
| `error_message` | TEXT | Error detail if failed | Yes | `Connection timeout` |

---

## Derived Fields Explained

| Field | Derivation Rule |
|-------|----------------|
| `severity_label` | Map `accident_severity` integer: 1→Fatal, 2→Serious, 3→Slight |
| `road_type_name` | Map `road_type` integer via `ROAD_TYPE_MAP` in config.py |
| `weather_description` | Map `weather_code` WMO integer via `WMO_WEATHER_DESCRIPTIONS` in config.py |
| `accident_hour` | Extract integer hour from `time` string (HH:MM) |
| `year`, `month`, `day` | Extract from `accident_date` using pandas `.dt` accessors |
| `weekday`, `weekday_name` | Extract from `accident_date` using `.dt.dayofweek` and `.dt.day_name()` |
| `weather_matched` | True if `temperature_2m` is not NULL after the left join |
| `join_grid_lat`, `join_grid_lon` | Snap `latitude`/`longitude` to nearest 0.5° grid cell |
