# Validation Rules — Traffic Accident Severity Analytics

This document defines every data-quality rule applied by the pipeline.
Each rule specifies: the column it checks, the condition for failure,
the action taken on failure, and the rationale for the decision.

Rules are implemented in `validation/validation_rules.py` and executed
by `validation/data_quality.py`.

---

## Rule Failure Actions

| Action | Meaning |
|--------|---------|
| `REJECT` | The row is moved to `data/rejected/` and excluded from the cleaned dataset. The pipeline continues. |
| `LOG_WARN` | The anomaly is logged and recorded in the quality report. The row is **retained**. The pipeline continues. |
| `FAIL_PIPELINE` | The pipeline halts immediately. This applies only to catastrophic failures (e.g. empty dataset). |

---

## Accident Dataset Rules

### 1. accident_row_count

| Attribute | Value |
|-----------|-------|
| **Check** | Cleaned accident DataFrame must not be empty |
| **Condition for FAIL** | `len(df) == 0` |
| **Action** | `FAIL_PIPELINE` |
| **Rationale** | An empty accident dataset indicates a fundamental ingestion failure. There is no point running any downstream steps. |

---

### 2. accident_id_not_null

| Attribute | Value |
|-----------|-------|
| **Column** | `accident_index` |
| **Check** | Every row must have a non-null, non-empty accident_index |
| **Condition for FAIL** | `accident_index IS NULL` or `accident_index = ''` |
| **Action** | `REJECT` |
| **Rationale** | The accident_index is the primary key and the join key for vehicle and casualty data. A row without an ID cannot be identified, linked, or verified. |
| **On failure** | Row written to `data/rejected/accidents_rejected.csv` with `rejection_reason = missing_accident_index` |

---

### 3. no_duplicate_accident_index

| Attribute | Value |
|-----------|-------|
| **Column** | `accident_index` |
| **Check** | Each accident_index value must appear exactly once |
| **Condition for FAIL** | `COUNT(DISTINCT accident_index) < COUNT(*)` |
| **Action** | `REJECT` |
| **Keep rule** | Keep first occurrence; reject all subsequent duplicates |
| **Rationale** | Duplicate records would inflate accident counts and distort severity statistics. STATS19 data should not contain duplicates; their presence suggests a data extraction issue. |

---

### 4. latitude_range

| Attribute | Value |
|-----------|-------|
| **Column** | `latitude` |
| **Check** | Latitude must be in the range −90 to +90 |
| **Condition for FAIL** | `latitude IS NULL` OR `latitude < −90` OR `latitude > 90` |
| **Action** | `REJECT` |
| **Rationale** | Latitude outside this range is physically impossible. A NULL latitude means the accident cannot be placed on a map and cannot be weather-enriched. |

---

### 5. longitude_range

| Attribute | Value |
|-----------|-------|
| **Column** | `longitude` |
| **Check** | Longitude must be in the range −180 to +180 |
| **Condition for FAIL** | `longitude IS NULL` OR `longitude < −180` OR `longitude > 180` |
| **Action** | `REJECT` |
| **Rationale** | Longitude outside this range is physically impossible. Same reasoning as latitude. |

---

### 6. accident_date_valid

| Attribute | Value |
|-----------|-------|
| **Column** | `accident_date` |
| **Check** | Date must be parseable and not null |
| **Condition for FAIL** | `accident_date IS NULL` (includes unparseable dates that become NaT) |
| **Action** | `REJECT` |
| **Rationale** | Date is required for time-series analysis, seasonal patterns, and joining with weather data. An accident without a date cannot be usefully analysed. |
| **STATS19 note** | Raw format is DD/MM/YYYY. The staging step converts this; failures produce NaT. |

---

### 7. accident_time_format

| Attribute | Value |
|-----------|-------|
| **Column** | `accident_time` |
| **Check** | Time should follow the pattern HH:MM |
| **Condition for FAIL** | Value does not match regex `^\d{1,2}:\d{2}$` |
| **Action** | `LOG_WARN` |
| **Rationale** | Time is important for hourly analysis and weather joining, but a row with a missing time is still geographically and severity-wise valid. Rejecting it would lose useful accident data. The hour is recorded as NULL and the accident is retained. |

---

### 8. severity_valid

| Attribute | Value |
|-----------|-------|
| **Column** | `accident_severity` |
| **Check** | Severity must be 1 (Fatal), 2 (Serious), or 3 (Slight) |
| **Condition for FAIL** | `accident_severity IS NULL` OR `accident_severity NOT IN (1, 2, 3)` |
| **Action** | `REJECT` |
| **Rationale** | Severity is the primary analytical dimension. An accident with unknown or invalid severity cannot be included in severity-based aggregations and would corrupt the analytical mart. |

---

### 9. vehicle_count_positive

| Attribute | Value |
|-----------|-------|
| **Column** | `number_of_vehicles` |
| **Check** | Vehicle count must be ≥ 1 when present |
| **Condition for FAIL** | `number_of_vehicles IS NOT NULL AND number_of_vehicles < 1` |
| **Action** | `LOG_WARN` |
| **Rationale** | An accident by definition involves at least one vehicle. A count of 0 suggests a data entry issue. However, this is rare and the record may still be analytically useful, so the row is retained with a warning logged. NULL vehicle count is allowed (not all STATS19 records have this populated). |

---

### 10. casualty_count_non_negative

| Attribute | Value |
|-----------|-------|
| **Column** | `number_of_casualties` |
| **Check** | Casualty count must be ≥ 0 when present |
| **Condition for FAIL** | `number_of_casualties IS NOT NULL AND number_of_casualties < 0` |
| **Action** | `REJECT` |
| **Rationale** | A negative casualty count is logically impossible and indicates data corruption. Unlike vehicle count (where 0 is marginal), a negative casualty count has no valid interpretation. |

---

### 11. uk_bounding_box (soft check)

| Attribute | Value |
|-----------|-------|
| **Columns** | `latitude`, `longitude` |
| **Check** | Coordinates should fall within the approximate UK bounding box: lat [49.8, 60.9], lon [−8.2, 1.8] |
| **Condition for FAIL** | Coordinates outside the box |
| **Action** | `LOG_WARN` |
| **Rationale** | STATS19 covers Great Britain, so coordinates should generally be within the UK. However, some legitimate records (Channel Islands, overseas British territories, data entry slight variations) may fall just outside. This is a warning, not a rejection. |

---

## Vehicle Dataset Rules

### 12. vehicle_accident_index_not_null

| Attribute | Value |
|-----------|-------|
| **Column** | `accident_index` |
| **Check** | Every vehicle row must reference a valid accident |
| **Condition for FAIL** | `accident_index IS NULL` |
| **Action** | `REJECT` |
| **Rationale** | Vehicle records without a parent accident_index are orphaned data that cannot be linked to any collision. |

---

### 13. vehicle_no_duplicates

| Attribute | Value |
|-----------|-------|
| **Columns** | `(accident_index, vehicle_reference)` |
| **Check** | Each (accident, vehicle) pair must be unique |
| **Condition for FAIL** | Duplicate (accident_index, vehicle_reference) pairs |
| **Action** | `REJECT` |
| **Rationale** | Each vehicle in each accident has a unique reference number. Duplicates indicate extraction errors. |

---

## Casualty Dataset Rules

### 14. casualty_accident_index_not_null

| Attribute | Value |
|-----------|-------|
| **Column** | `accident_index` |
| **Check** | Every casualty row must reference a valid accident |
| **Condition for FAIL** | `accident_index IS NULL` |
| **Action** | `REJECT` |

---

### 15. casualty_severity_valid

| Attribute | Value |
|-----------|-------|
| **Column** | `casualty_severity` |
| **Check** | Casualty severity must be 1, 2, or 3 when present |
| **Condition for FAIL** | `casualty_severity IS NOT NULL AND casualty_severity NOT IN (1, 2, 3)` |
| **Action** | `REJECT` |
| **Rationale** | NULL casualty severity is allowed (severity may be recorded at accident level). An explicit invalid code is rejected. |

---

## Weather Dataset Rules

### 16. weather_row_count

| Attribute | Value |
|-----------|-------|
| **Check** | Weather dataset must not be empty |
| **Condition for FAIL** | `len(df) == 0` |
| **Action** | `LOG_WARN` |
| **Rationale** | Missing weather data is non-fatal. The pipeline continues with NULL weather columns in the mart. |

### 17. weather_datetime_not_null

| Attribute | Value |
|-----------|-------|
| **Column** | `datetime` |
| **Check** | All weather rows must have a valid datetime |
| **Action** | `LOG_WARN` |

### 18. weather_temperature_plausible

| Attribute | Value |
|-----------|-------|
| **Column** | `temperature_2m` |
| **Check** | Temperature should be in the range −30°C to +45°C |
| **Condition for FAIL** | Outside this range when not NULL |
| **Action** | `LOG_WARN` |
| **Rationale** | Open-Meteo data is generally clean. Implausible temperatures suggest an API error or location mismatch. Warning only — the accident is still retained. |

---

## Quality Report Format

After every pipeline run, `validation/data_quality.py` outputs:

```
════════════════════════════════════════════════════════════
  DATA QUALITY REPORT — 2023-01-15 14:30:00
════════════════════════════════════════════════════════════
  Dataset       : ACCIDENTS
  Total Records : 100,245
────────────────────────────────────────────────────────────
  [PASS] accident_row_count               Dataset contains 100,245 rows
  [PASS] accident_id_not_null             All accident_index values present
  [PASS] no_duplicate_accident_index      No duplicates found
  [PASS] latitude_range                   All latitudes in [-90, 90]
  [PASS] longitude_range                  All longitudes in [-180, 180]
  [PASS] accident_date_valid              All dates are valid
  [PASS] accident_time_format             All times in HH:MM format
  [PASS] severity_valid                   All severity values in {1, 2, 3}
  [PASS] vehicle_count_positive           All vehicle counts >= 1
  [PASS] casualty_count_non_negative      All casualty counts >= 0
  [FAIL] uk_bounding_box                  12 accidents outside UK box [LOG_WARN]
────────────────────────────────────────────────────────────
  Checks Passed  : 10
  Checks Failed  : 1  (LOG_WARN — pipeline continues)
  Rejected Rows  : 0
════════════════════════════════════════════════════════════
```

The JSON version of this report is saved to `data/rejected/quality_report_accidents_<timestamp>.json`.
