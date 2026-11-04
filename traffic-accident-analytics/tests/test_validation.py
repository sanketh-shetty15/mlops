"""
tests/test_validation.py
--------------------------
Unit tests for all data-quality validation rules.

Every rule function is tested with:
  - a PASSING dataset (expected: result.passed == True)
  - a FAILING dataset (expected: result.passed == False, correct failed_count)

No live database or external API is needed.

Run with:
    pytest tests/test_validation.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pandas as pd
import numpy as np

from validation.validation_rules import (
    rule_accident_row_count,
    rule_accident_id_not_null,
    rule_no_duplicate_accident_index,
    rule_latitude_range,
    rule_longitude_range,
    rule_accident_date_valid,
    rule_accident_time_format,
    rule_severity_valid,
    rule_vehicle_count_positive,
    rule_casualty_count_non_negative,
    rule_uk_bounding_box,
    rule_casualty_severity_valid,
    rule_weather_row_count,
    rule_weather_datetime_not_null,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _good_accidents(n=10) -> pd.DataFrame:
    """Return a minimal valid accident DataFrame."""
    # Build severity cycle that always has correct length
    sev_cycle = [1, 2, 3]
    severities = [sev_cycle[i % 3] for i in range(n)]
    return pd.DataFrame({
        "accident_index":      [f"2023{i:08d}" for i in range(n)],
        "accident_date":       pd.date_range("2023-01-01", periods=n, freq="D"),
        "accident_time":       ["08:30"] * n,
        "accident_severity":   pd.array(severities, dtype="Int64"),
        "latitude":            [51.5 + i * 0.01 for i in range(n)],
        "longitude":           [-0.1 + i * 0.01 for i in range(n)],
        "number_of_vehicles":  [2] * n,
        "number_of_casualties":[1] * n,
    })


# ── rule_accident_row_count ────────────────────────────────────────────────────

class TestRowCount:
    def test_passes_on_non_empty(self):
        result = rule_accident_row_count(_good_accidents())
        assert result.passed is True

    def test_fails_on_empty(self):
        result = rule_accident_row_count(pd.DataFrame())
        assert result.passed is False
        assert result.action == "FAIL_PIPELINE"


# ── rule_accident_id_not_null ──────────────────────────────────────────────────

class TestAccidentIdNotNull:
    def test_passes_all_ids_present(self):
        result = rule_accident_id_not_null(_good_accidents())
        assert result.passed is True
        assert result.failed_count == 0

    def test_fails_when_id_is_null(self):
        df = _good_accidents()
        df.loc[0, "accident_index"] = None
        result = rule_accident_id_not_null(df)
        assert result.passed is False
        assert result.failed_count == 1

    def test_fails_when_id_is_empty_string(self):
        df = _good_accidents()
        df.loc[2, "accident_index"] = ""
        result = rule_accident_id_not_null(df)
        assert result.passed is False

    def test_fails_when_column_missing(self):
        df = _good_accidents().drop(columns=["accident_index"])
        result = rule_accident_id_not_null(df)
        assert result.passed is False
        assert result.action == "FAIL_PIPELINE"

    def test_failed_count_matches_null_count(self):
        df = _good_accidents(6)
        df.loc[[0, 3], "accident_index"] = None
        result = rule_accident_id_not_null(df)
        assert result.failed_count == 2


# ── rule_no_duplicate_accident_index ──────────────────────────────────────────

class TestNoDuplicates:
    def test_passes_unique_ids(self):
        result = rule_no_duplicate_accident_index(_good_accidents())
        assert result.passed is True

    def test_fails_with_one_duplicate(self):
        df = _good_accidents(5)
        df.loc[4, "accident_index"] = df.loc[0, "accident_index"]
        result = rule_no_duplicate_accident_index(df)
        assert result.passed is False
        assert result.failed_count == 1

    def test_fails_with_multiple_duplicates(self):
        df = _good_accidents(6)
        df.loc[3, "accident_index"] = df.loc[0, "accident_index"]
        df.loc[5, "accident_index"] = df.loc[1, "accident_index"]
        result = rule_no_duplicate_accident_index(df)
        assert result.failed_count == 2


# ── rule_latitude_range ────────────────────────────────────────────────────────

class TestLatitudeRange:
    def test_passes_valid_uk_lat(self):
        result = rule_latitude_range(_good_accidents())
        assert result.passed is True

    def test_fails_above_90(self):
        df = _good_accidents(3)
        df.loc[1, "latitude"] = 95.0
        result = rule_latitude_range(df)
        assert result.passed is False
        assert result.failed_count == 1

    def test_fails_below_minus_90(self):
        df = _good_accidents(3)
        df.loc[0, "latitude"] = -91.0
        result = rule_latitude_range(df)
        assert result.passed is False

    def test_fails_on_null_latitude(self):
        df = _good_accidents(4)
        df.loc[2, "latitude"] = None
        result = rule_latitude_range(df)
        assert result.passed is False
        assert result.failed_count == 1

    def test_boundary_exactly_90_passes(self):
        df = _good_accidents(2)
        df.loc[0, "latitude"] = 90.0
        df.loc[1, "latitude"] = -90.0
        result = rule_latitude_range(df)
        assert result.passed is True


# ── rule_longitude_range ───────────────────────────────────────────────────────

class TestLongitudeRange:
    def test_passes_valid_uk_lon(self):
        result = rule_longitude_range(_good_accidents())
        assert result.passed is True

    def test_fails_above_180(self):
        df = _good_accidents(3)
        df.loc[0, "longitude"] = 181.0
        result = rule_longitude_range(df)
        assert result.passed is False
        assert result.failed_count == 1

    def test_fails_below_minus_180(self):
        df = _good_accidents(3)
        df.loc[0, "longitude"] = -181.5
        result = rule_longitude_range(df)
        assert result.passed is False

    def test_fails_on_null_longitude(self):
        df = _good_accidents(3)
        df.loc[1, "longitude"] = float("nan")
        result = rule_longitude_range(df)
        assert result.passed is False


# ── rule_accident_date_valid ───────────────────────────────────────────────────

class TestAccidentDateValid:
    def test_passes_valid_dates(self):
        result = rule_accident_date_valid(_good_accidents())
        assert result.passed is True

    def test_fails_on_null_date(self):
        df = _good_accidents(5)
        df.loc[2, "accident_date"] = None
        result = rule_accident_date_valid(df)
        assert result.passed is False
        assert result.failed_count == 1

    def test_fails_on_unparseable_string(self):
        df = _good_accidents(3)
        df["accident_date"] = df["accident_date"].astype(str)
        df.loc[1, "accident_date"] = "not-a-date"
        result = rule_accident_date_valid(df)
        assert result.passed is False


# ── rule_accident_time_format ──────────────────────────────────────────────────

class TestAccidentTimeFormat:
    def test_passes_valid_times(self):
        result = rule_accident_time_format(_good_accidents())
        assert result.passed is True

    def test_fails_malformed_time(self):
        df = _good_accidents(4)
        df.loc[0, "accident_time"] = "2537"       # missing colon
        result = rule_accident_time_format(df)
        assert result.passed is False
        assert result.failed_count >= 1

    def test_action_is_log_warn(self):
        """Time format failure should only warn, not reject."""
        df = _good_accidents(3)
        df.loc[0, "accident_time"] = "bad"
        result = rule_accident_time_format(df)
        assert result.action == "LOG_WARN"


# ── rule_severity_valid ────────────────────────────────────────────────────────

class TestSeverityValid:
    def test_passes_valid_severities_1_2_3(self):
        result = rule_severity_valid(_good_accidents())
        assert result.passed is True

    def test_fails_on_code_4(self):
        df = _good_accidents(4)
        df.loc[1, "accident_severity"] = 4
        result = rule_severity_valid(df)
        assert result.passed is False
        assert result.failed_count == 1

    def test_fails_on_null_severity(self):
        df = _good_accidents(4)
        df.loc[0, "accident_severity"] = None
        result = rule_severity_valid(df)
        assert result.passed is False

    def test_fails_on_zero(self):
        df = _good_accidents(3)
        df.loc[2, "accident_severity"] = 0
        result = rule_severity_valid(df)
        assert result.passed is False

    def test_all_three_valid_codes_pass(self):
        df = pd.DataFrame({
            "accident_severity": pd.array([1, 2, 3])
        })
        result = rule_severity_valid(df)
        assert result.passed is True
        assert result.failed_count == 0


# ── rule_vehicle_count_positive ───────────────────────────────────────────────

class TestVehicleCountPositive:
    def test_passes_positive_counts(self):
        result = rule_vehicle_count_positive(_good_accidents())
        assert result.passed is True

    def test_warns_on_zero(self):
        df = _good_accidents(3)
        df.loc[0, "number_of_vehicles"] = 0
        result = rule_vehicle_count_positive(df)
        assert result.passed is False
        assert result.action == "LOG_WARN"

    def test_null_counts_are_ignored(self):
        """NULL vehicle count is not a rejection — just unknown."""
        df = _good_accidents(3)
        df.loc[1, "number_of_vehicles"] = None
        result = rule_vehicle_count_positive(df)
        assert result.passed is True


# ── rule_casualty_count_non_negative ──────────────────────────────────────────

class TestCasualtyCountNonNegative:
    def test_passes_non_negative_counts(self):
        result = rule_casualty_count_non_negative(_good_accidents())
        assert result.passed is True

    def test_fails_on_negative(self):
        df = _good_accidents(4)
        df.loc[2, "number_of_casualties"] = -1
        result = rule_casualty_count_non_negative(df)
        assert result.passed is False
        assert result.failed_count == 1

    def test_zero_casualties_is_valid(self):
        """An accident with 0 casualties is valid (property damage only)."""
        df = _good_accidents(3)
        df.loc[0, "number_of_casualties"] = 0
        result = rule_casualty_count_non_negative(df)
        assert result.passed is True


# ── rule_uk_bounding_box ──────────────────────────────────────────────────────

class TestUKBoundingBox:
    def test_passes_uk_coords(self):
        result = rule_uk_bounding_box(_good_accidents())
        assert result.passed is True

    def test_warns_on_outside_uk(self):
        df = _good_accidents(3)
        df.loc[0, "latitude"]  = 20.0   # Africa
        df.loc[0, "longitude"] = 30.0
        result = rule_uk_bounding_box(df)
        assert result.passed is False
        assert result.action == "LOG_WARN"
        assert result.failed_count == 1


# ── rule_casualty_severity_valid ──────────────────────────────────────────────

class TestCasualtySeverityValid:
    def _make_cas(self, severities):
        return pd.DataFrame({
            "accident_index":    [f"IDX{i}" for i in range(len(severities))],
            "casualty_severity": pd.array(severities),
        })

    def test_passes_valid_severities(self):
        result = rule_casualty_severity_valid(self._make_cas([1, 2, 3, 1]))
        assert result.passed is True

    def test_fails_on_code_5(self):
        result = rule_casualty_severity_valid(self._make_cas([1, 5, 2]))
        assert result.passed is False
        assert result.failed_count == 1

    def test_null_severity_is_allowed(self):
        """NULL casualty severity = unknown, not invalid."""
        df = self._make_cas([1, 2, 3])
        df.loc[1, "casualty_severity"] = None
        result = rule_casualty_severity_valid(df)
        assert result.passed is True


# ── rule_weather_row_count ────────────────────────────────────────────────────

class TestWeatherRowCount:
    def test_passes_non_empty(self):
        df = pd.DataFrame({"datetime": pd.date_range("2023-01-01", periods=5, freq="h")})
        result = rule_weather_row_count(df)
        assert result.passed is True

    def test_fails_empty(self):
        result = rule_weather_row_count(pd.DataFrame())
        assert result.passed is False
        assert result.action == "LOG_WARN"   # non-fatal


# ── rule_weather_datetime_not_null ────────────────────────────────────────────

class TestWeatherDatetimeNotNull:
    def test_passes_all_datetimes_present(self):
        df = pd.DataFrame({
            "datetime": pd.date_range("2023-01-01", periods=5, freq="h"),
        })
        result = rule_weather_datetime_not_null(df)
        assert result.passed is True

    def test_fails_null_datetime(self):
        df = pd.DataFrame({
            "datetime": [pd.Timestamp("2023-01-01"), None, pd.Timestamp("2023-01-03")],
        })
        result = rule_weather_datetime_not_null(df)
        assert result.passed is False
        assert result.failed_count == 1


# ── run_checks integration ────────────────────────────────────────────────────

class TestRunChecks:
    def test_returns_summary_dict(self):
        from validation.data_quality import run_checks
        from validation.validation_rules import ACCIDENT_RULES

        df = _good_accidents(20)
        summary = run_checks(df, ACCIDENT_RULES, "test_accidents")

        assert "dataset"       in summary
        assert "total_records" in summary
        assert "checks_passed" in summary
        assert "checks_failed" in summary
        assert "pipeline_halt" in summary
        assert summary["dataset"]       == "test_accidents"
        assert summary["total_records"] == 20

    def test_all_pass_on_clean_data(self):
        from validation.data_quality import run_checks
        from validation.validation_rules import ACCIDENT_RULES

        df = _good_accidents(50)
        summary = run_checks(df, ACCIDENT_RULES, "test_accidents")
        assert summary["checks_failed"] == 0
        assert summary["pipeline_halt"] is False

    def test_fail_detected_on_bad_data(self):
        from validation.data_quality import run_checks
        from validation.validation_rules import ACCIDENT_RULES

        df = _good_accidents(10)
        df.loc[[0, 1], "accident_index"] = None   # force 2 bad rows
        summary = run_checks(df, ACCIDENT_RULES, "test_accidents")
        assert summary["checks_failed"] > 0
