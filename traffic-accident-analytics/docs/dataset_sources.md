# Dataset Sources — Traffic Accident Severity Analytics

This document describes every data source used in the project,
how to access it, and what fields are extracted.

---

## Source 1: UK Road Safety Open Data (STATS19)

| Attribute | Value |
|-----------|-------|
| **Source Name** | UK Road Safety Open Data — STATS19 |
| **Publisher** | Department for Transport (DfT), UK Government |
| **Purpose** | Primary accident dataset — one row per reported personal-injury collision |
| **Access Method** | Direct CSV download (no authentication required) |
| **Licence** | Open Government Licence v3.0 |
| **Update frequency** | Annual (final data released ~July) |
| **Coverage** | Great Britain, 1979 to present |

### Access Instructions

1. Go to: https://www.gov.uk/government/statistical-data-sets/road-safety-open-data
2. Under **"2023"**, download the three CSV files:
   - `Road Safety Data - Collisions - 2023` (≈ 20 MB)
   - `Road Safety Data - Vehicles - 2023` (≈ 20 MB)
   - `Road Safety Data - Casualties - 2023` (≈ 11 MB)
3. Place the files in:
   ```
   data/raw/accidents/dft-road-casualty-statistics-collision-2023.csv
   data/raw/vehicles/dft-road-casualty-statistics-vehicle-2023.csv
   data/raw/casualties/dft-road-casualty-statistics-casualty-2023.csv
   ```

**Alternatively**, run the ingestion script which will attempt to download
them automatically:
```bash
python ingestion/accident_ingestion.py
python ingestion/vehicle_ingestion.py
python ingestion/casualty_ingestion.py
```

### Data Guide

The DfT publishes a coded data guide (Excel file) that maps numeric codes
to descriptions. It is available on the same page as the CSV downloads.
The pipeline uses `config.py` to maintain the most important mappings
(severity, road type) directly.

### Collision File — Key Columns

| Column | Type | Description |
|--------|------|-------------|
| `accident_index` | string | Unique collision identifier (primary key) |
| `accident_year` | int | Year of accident |
| `date` | string (DD/MM/YYYY) | Date of accident |
| `time` | string (HH:MM) | Time of accident |
| `accident_severity` | int | 1=Fatal, 2=Serious, 3=Slight |
| `number_of_vehicles` | int | Vehicles involved |
| `number_of_casualties` | int | Casualties |
| `latitude` | float | WGS84 latitude |
| `longitude` | float | WGS84 longitude |
| `road_type` | int | Road type code (1-9) |
| `speed_limit` | int | Posted speed limit (mph) |
| `junction_detail` | int | Junction type code |
| `light_conditions` | int | Light conditions code |
| `weather_conditions` | int | STATS19 weather code (different from Open-Meteo) |
| `road_surface_conditions` | int | Surface condition code |
| `urban_or_rural_area` | int | 1=Urban, 2=Rural |
| `local_authority_district` | int | Local authority code |

**Note on missing values:** STATS19 uses −1 to represent "Data missing or
out of range". The staging step replaces all −1 values with NULL.

### Vehicle File — Key Columns

| Column | Type | Description |
|--------|------|-------------|
| `accident_index` | string | Foreign key → collision |
| `vehicle_reference` | int | Vehicle number within the accident |
| `vehicle_type` | int | Vehicle type code |
| `age_of_driver` | float | Driver age (years) |
| `sex_of_driver` | int | 1=Male, 2=Female |
| `age_of_vehicle` | float | Vehicle age (years) |
| `engine_capacity_cc` | float | Engine capacity |
| `propulsion_code` | int | Fuel/propulsion type |
| `journey_purpose_of_driver` | int | Journey purpose code |

### Casualty File — Key Columns

| Column | Type | Description |
|--------|------|-------------|
| `accident_index` | string | Foreign key → collision |
| `vehicle_reference` | int | Vehicle involved |
| `casualty_reference` | int | Casualty number within accident |
| `casualty_class` | int | 1=Driver/rider, 2=Passenger, 3=Pedestrian |
| `sex_of_casualty` | int | 1=Male, 2=Female |
| `age_of_casualty` | float | Age (years) |
| `casualty_severity` | int | 1=Fatal, 2=Serious, 3=Slight |
| `casualty_type` | int | Casualty type code |

---

## Source 2: Open-Meteo Historical Weather API

| Attribute | Value |
|-----------|-------|
| **Source Name** | Open-Meteo Historical Weather API |
| **Publisher** | Open-Meteo (open-source, non-commercial) |
| **Purpose** | Hourly weather observations matched to accident time and location |
| **Access Method** | REST API (HTTPS GET) — no API key required |
| **Licence** | Open-source, non-commercial use free |
| **Coverage** | Global, 1940 to present (ERA5 reanalysis) |
| **Base URL** | `https://archive-api.open-meteo.com/v1/archive` |

### Extraction Method

The pipeline uses a **grid-snapping + caching strategy** to minimise
API calls:

1. Each accident's `(latitude, longitude)` is rounded to the nearest
   **0.5-degree grid cell** (configurable in `config.py`).
2. For each unique grid cell, **one API request** fetches all hourly
   weather data for the entire year (e.g. 8,760 rows for 2023).
3. The response is cached as a **Parquet file** in `data/raw/weather/`.
4. Subsequent pipeline runs read from the cache — no API call is made
   for cells already cached.

For the full UK 2023 dataset (approximately 80–120 unique 0.5° grid
cells), this results in approximately 80–120 API calls total, not
100,000+ calls.

### API Parameters Used

```
GET https://archive-api.open-meteo.com/v1/archive
  ?latitude=51.5
  &longitude=-0.0
  &start_date=2023-01-01
  &end_date=2023-12-31
  &hourly=temperature_2m,precipitation,rain,snowfall,
          weather_code,wind_speed_10m,wind_direction_10m,
          relative_humidity_2m,visibility,cloud_cover
  &timezone=UTC
  &wind_speed_unit=mph
```

### Weather Variables Extracted

| Variable | Unit | Description |
|----------|------|-------------|
| `temperature_2m` | °C | Air temperature at 2 m height |
| `precipitation` | mm | Total precipitation (rain + snow) |
| `rain` | mm | Rain component only |
| `snowfall` | cm | Snowfall |
| `weather_code` | WMO | WMO weather condition code (0–99) |
| `wind_speed_10m` | mph | Wind speed at 10 m height |
| `wind_direction_10m` | degrees | Wind direction |
| `relative_humidity_2m` | % | Relative humidity at 2 m |
| `visibility` | m | Visibility |
| `cloud_cover` | % | Cloud cover |

### WMO Weather Code Mapping (selected)

| Code | Description |
|------|-------------|
| 0 | Clear sky |
| 1–3 | Mainly clear / Partly cloudy / Overcast |
| 45, 48 | Foggy / Rime fog |
| 51, 53, 55 | Drizzle (light / moderate / dense) |
| 61, 63, 65 | Rain (slight / moderate / heavy) |
| 71, 73, 75 | Snow (slight / moderate / heavy) |
| 80, 81, 82 | Rain showers (slight / moderate / violent) |
| 95 | Thunderstorm |

Full mapping in `config.py → WMO_WEATHER_DESCRIPTIONS`.

### Weather–Accident Join Strategy

- **Grid snap:** Accident `(lat, lon)` → nearest 0.5° grid cell
- **Hour matching:** Accident time `HH:MM` → nearest integer hour
  (e.g. 08:37 → 09:00; 08:22 → 08:00)
- **Join type:** LEFT JOIN — accidents without matching weather keep
  `NULL` weather columns. No accidents are discarded.
- **Match rate:** Depends on how many grid cells were successfully
  cached. Typically > 95% when all grid cells are fetched.

---

## Source 3: OpenStreetMap (Optional — Not Yet Implemented)

| Attribute | Value |
|-----------|-------|
| **Source Name** | OpenStreetMap / Nominatim |
| **Purpose** | Road name / area name enrichment for locations |
| **Status** | Not implemented in Part 1 |
| **Note** | Could be added in a future version to enrich `dim_location` with road names via reverse geocoding |

---

## Data Licensing Summary

| Source | Licence | Attribution Required |
|--------|---------|---------------------|
| UK STATS19 (DfT) | Open Government Licence v3.0 | Yes — "Contains public sector information licensed under the Open Government Licence v3.0" |
| Open-Meteo | Creative Commons Attribution 4.0 | Yes — "Weather data by Open-Meteo.com" |
| OpenStreetMap | ODbL | Yes (if used) |
