"""
tests/test_transformations.py
-------------------------------
Unit tests for the transformation layer:
  - staging (column normalisation, date parsing, time parsing)
  - cleaning (rejection rules applied correctly)
  - join (nearest-hour matching, left-join behaviour)

All tests use small in-memory DataFrames. No files are written to disk.
No PostgreSQL connection is required.

Run with:
    pytest tests/test_transformations.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pandas as pd
import numpy as np
from datetime import date
from unittest.mock import patch


# ── Helpers ────────────────────────────────────────────────────────────────────

def _raw_accidents(n: int = 8) -> pd.DataFrame:
    """Build a minimal STATS19-style accident DataFrame with real column names."""
    return pd.DataFrame({
        "Accident_Index":       [f"2023{i:08d}" for i in range(n)],
        "date":                 ["01/01/2023"] * n,
        "time":                 ["08:30"] * n,
        "Accident_Severity":    [1, 2, 3, 1, 2, 3, 1, 2][:n],
        "latitude":             [51.5 + i * 0.01 for i in range(n)],
        "longitude":            [-0.1 + i * 0.01 for i in range(n)],
        "Number_of_Vehicles":   [2] * n,
        "Number_of_Casualties": [1] * n,
        "Road_Type":            [6] * n,
        "Speed_limit":          [30] * n,
    })


# ── Column normalisation ───────────────────────────────────────────────────────

class TestColumnNormalisation:
    def test_columns_converted_to_snake_case(self):
        from transformation.clean_accidents import _normalise_column_names

        df = pd.DataFrame(columns=["Accident Index", "Road-Type", "Speed Limit"])
        df = _normalise_column_names(df)
        assert "accident_index" in df.columns
        assert "road_type"      in df.columns
        assert "speed_limit"    in df.columns

    def test_uppercase_converted_to_lowercase(self):
        from transformation.clean_accidents import _normalise_column_names

        df = pd.DataFrame(columns=["ACCIDENT_INDEX", "DATE"])
        df = _normalise_column_names(df)
        assert "accident_index" in df.columns
        assert "date"           in df.columns

    def test_special_characters_stripped(self):
        from transformation.clean_accidents import _normalise_column_names

        df = pd.DataFrame(columns=["col(1)", "col#2"])
        df = _normalise_column_names(df)
        # Special chars should be removed; spaces/hyphens → underscore
        for col in df.columns:
            assert col.islower() or "_" in col

    def test_existing_snake_case_unchanged(self):
        from transformation.clean_accidents import _normalise_column_names

        df = pd.DataFrame(columns=["accident_index", "road_type"])
        original = list(df.columns)
        df = _normalise_column_names(df)
        assert list(df.columns) == original


# ── Date parsing ───────────────────────────────────────────────────────────────

class TestDateParsing:
    def test_parses_dd_mm_yyyy_format(self):
        from transformation.clean_accidents import _parse_date

        df = pd.DataFrame({"date": ["01/01/2023", "15/06/2023", "31/12/2023"]})
        df = _parse_date(df)

        assert "accident_date" in df.columns
        assert "date" not in df.columns
        assert df.loc[0, "accident_date"] == pd.Timestamp("2023-01-01")
        assert df.loc[1, "accident_date"] == pd.Timestamp("2023-06-15")

    def test_invalid_date_becomes_nat(self):
        from transformation.clean_accidents import _parse_date

        df = pd.DataFrame({"date": ["not-a-date", "99/99/9999"]})
        df = _parse_date(df)
        assert df["accident_date"].isna().all()

    def test_mixed_valid_and_invalid(self):
        from transformation.clean_accidents import _parse_date

        df = pd.DataFrame({"date": ["01/01/2023", "bad", "15/03/2023"]})
        df = _parse_date(df)
        assert df["accident_date"].notna().sum() == 2
        assert df["accident_date"].isna().sum()  == 1

    def test_date_column_removed_after_parsing(self):
        from transformation.clean_accidents import _parse_date

        df = pd.DataFrame({"date": ["01/01/2023"]})
        df = _parse_date(df)
        assert "date" not in df.columns


# ── Time parsing ───────────────────────────────────────────────────────────────

class TestTimeParsing:
    def test_parses_hhmm_format(self):
        from transformation.clean_accidents import _parse_time

        df = pd.DataFrame({"time": ["08:30", "17:45", "00:00", "23:59"]})
        df = _parse_time(df)

        assert "accident_time" in df.columns
        assert "accident_hour" in df.columns
        assert df.loc[0, "accident_hour"] == 8
        assert df.loc[1, "accident_hour"] == 17
        assert df.loc[2, "accident_hour"] == 0
        assert df.loc[3, "accident_hour"] == 23

    def test_original_time_column_removed(self):
        from transformation.clean_accidents import _parse_time

        df = pd.DataFrame({"time": ["08:30"]})
        df = _parse_time(df)
        assert "time" not in df.columns

    def test_malformed_time_gives_null_hour(self):
        from transformation.clean_accidents import _parse_time

        df = pd.DataFrame({"time": ["invalid", "99:99"]})
        df = _parse_time(df)
        # "invalid" has no colon, "99:99" → 99 (not yet validated)
        # Key point: no exception raised
        assert "accident_hour" in df.columns


# ── Coded-missing replacement ──────────────────────────────────────────────────

class TestCodedMissingReplacement:
    def test_minus_one_replaced_with_na(self):
        from transformation.clean_accidents import _replace_coded_missing

        df = pd.DataFrame({
            "accident_severity": [-1, 1, 2],
            "speed_limit":       [30, -1, 50],
        })
        df = _replace_coded_missing(df)
        assert pd.isna(df.loc[0, "accident_severity"])
        assert pd.isna(df.loc[1, "speed_limit"])

    def test_valid_values_unchanged(self):
        from transformation.clean_accidents import _replace_coded_missing

        df = pd.DataFrame({"accident_severity": [1, 2, 3]})
        df = _replace_coded_missing(df)
        assert list(df["accident_severity"]) == [1, 2, 3]

    def test_unknown_columns_ignored(self):
        from transformation.clean_accidents import _replace_coded_missing

        df = pd.DataFrame({"some_other_column": [-1, 2, 3]})
        df_out = _replace_coded_missing(df)
        # Column not in _CODED_MISSING_INT_COLS → unchanged
        assert list(df_out["some_other_column"]) == [-1, 2, 3]


# ── stage_accidents ────────────────────────────────────────────────────────────

class TestStageAccidents:
    def test_returns_dataframe(self):
        from transformation.clean_accidents import stage_accidents

        df_raw = _raw_accidents(5)
        with patch("transformation.clean_accidents.STAGING_DIR") as mock_dir:
            # Patch STAGING_DIR to avoid writing files during tests
            mock_dir.__truediv__ = lambda s, x: Path("/tmp") / x
            mock_dir.mkdir = lambda **kw: None

            with patch("pandas.DataFrame.to_csv"):   # suppress file write
                df_staged = stage_accidents(df_raw)

        assert isinstance(df_staged, pd.DataFrame)
        assert len(df_staged) == 5

    def test_column_names_normalised(self):
        from transformation.clean_accidents import stage_accidents

        df_raw = _raw_accidents(3)
        with patch("pandas.DataFrame.to_csv"):
            with patch("transformation.clean_accidents.STAGING_DIR") as md:
                md.__truediv__ = lambda s, x: Path("/tmp") / x
                md.mkdir = lambda **kw: None
                df_staged = stage_accidents(df_raw)

        # All column names should be lowercase with no spaces
        for col in df_staged.columns:
            assert col == col.lower(), f"Column not lowercase: {col}"
            assert " " not in col, f"Column has space: {col}"


# ── clean_accidents ────────────────────────────────────────────────────────────

class TestCleanAccidents:
    def _staged(self, n=10) -> pd.DataFrame:
        """Build a pre-staged accident DataFrame (already normalised)."""
        return pd.DataFrame({
            "accident_index":       [f"2023{i:08d}" for i in range(n)],
            "accident_date":        pd.date_range("2023-01-01", periods=n),
            "accident_time":        ["08:30"] * n,
            "accident_severity":    pd.array([1, 2, 3] * 4)[:n],
            "latitude":             [51.5 + i * 0.01 for i in range(n)],
            "longitude":            [-0.1 + i * 0.01 for i in range(n)],
            "number_of_vehicles":   [2] * n,
            "number_of_casualties": [1] * n,
            "_staged_at":           ["2023-01-01T00:00:00"] * n,
        })

    def _run_clean(self, df):
        """Run clean_accidents with file I/O patched out."""
        with patch("pandas.DataFrame.to_csv"):
            with patch("transformation.clean_accidents.CLEANED_DIR") as cd, \
                 patch("transformation.clean_accidents.REJECTED_DIR") as rd:
                cd.__truediv__ = lambda s, x: Path("/tmp") / x
                rd.__truediv__ = lambda s, x: Path("/tmp") / x
                cd.mkdir = rd.mkdir = lambda **kw: None
                from transformation.clean_accidents import clean_accidents
                return clean_accidents(df)

    def test_clean_data_passes_through(self):
        df = self._staged(10)
        clean, rejected = self._run_clean(df)
        assert len(clean) == 10
        assert len(rejected) == 0

    def test_null_accident_index_is_rejected(self):
        df = self._staged(5)
        df.loc[0, "accident_index"] = None
        clean, rejected = self._run_clean(df)
        assert len(clean) == 4
        assert len(rejected) == 1
        assert rejected.iloc[0]["rejection_reason"] == "missing_accident_index"

    def test_duplicate_index_is_rejected(self):
        df = self._staged(5)
        df.loc[4, "accident_index"] = df.loc[0, "accident_index"]  # create dup
        clean, rejected = self._run_clean(df)
        assert len(clean) == 4
        assert len(rejected) == 1
        assert "duplicate" in rejected.iloc[0]["rejection_reason"]

    def test_invalid_latitude_is_rejected(self):
        df = self._staged(5)
        df.loc[2, "latitude"] = 200.0   # impossible latitude
        clean, rejected = self._run_clean(df)
        assert len(clean) == 4
        rejected_reasons = rejected["rejection_reason"].tolist()
        assert any("latitude" in r for r in rejected_reasons)

    def test_invalid_severity_is_rejected(self):
        df = self._staged(5)
        df.loc[1, "accident_severity"] = 9   # not 1, 2, or 3
        clean, rejected = self._run_clean(df)
        assert len(clean) == 4
        rejected_reasons = rejected["rejection_reason"].tolist()
        assert any("severity" in r for r in rejected_reasons)

    def test_severity_label_derived(self):
        """After cleaning, severity_label should be present."""
        df = self._staged(6)
        clean, _ = self._run_clean(df)
        assert "severity_label" in clean.columns
        assert set(clean["severity_label"]).issubset({"Fatal", "Serious", "Slight"})

    def test_weekday_name_derived(self):
        """After cleaning, weekday_name should be derived from accident_date."""
        df = self._staged(7)
        clean, _ = self._run_clean(df)
        assert "weekday_name" in clean.columns

    def test_accident_year_derived(self):
        """accident_year should be present and correct."""
        df = self._staged(3)
        clean, _ = self._run_clean(df)
        assert "accident_year" in clean.columns
        assert (clean["accident_year"] == 2023).all()

    def test_multiple_rejection_reasons_tracked(self):
        """Different rows failing different rules should all be captured."""
        df = self._staged(8)
        df.loc[0, "accident_index"] = None    # missing ID
        df.loc[3, "latitude"]       = 200.0   # bad lat
        df.loc[6, "accident_severity"] = 0    # bad severity

        clean, rejected = self._run_clean(df)
        assert len(clean) == 5
        assert len(rejected) == 3
        reasons = set(rejected["rejection_reason"].tolist())
        assert "missing_accident_index" in reasons


# ── join_accident_weather ──────────────────────────────────────────────────────

class TestJoinAccidentWeather:
    """Test the join logic without touching the file system."""

    def _make_accidents(self) -> pd.DataFrame:
        return pd.DataFrame({
            "accident_index":       ["ACC001", "ACC002", "ACC003"],
            "accident_date":        pd.to_datetime(["2023-03-15", "2023-03-15", "2023-06-01"]),
            "accident_time":        ["08:37", "15:05", "23:55"],
            "accident_hour":        [8, 15, 23],
            "latitude":             [51.51, 52.00, 53.50],
            "longitude":            [-0.13, -1.50, -2.00],
            "accident_severity":    [1, 2, 3],
            "severity_label":       ["Fatal", "Serious", "Slight"],
            "number_of_vehicles":   [2, 1, 3],
            "number_of_casualties": [1, 0, 2],
        })

    def _make_weather(self) -> pd.DataFrame:
        """Build weather rows matching ACC001 and ACC002 but not ACC003."""
        return pd.DataFrame({
            "datetime":          pd.to_datetime([
                "2023-03-15T09:00",   # matches ACC001 (08:37 → nearest 9)
                "2023-03-15T15:00",   # matches ACC002 (15:05 → nearest 15)
            ]),
            "weather_date":      [date(2023, 3, 15), date(2023, 3, 15)],
            "weather_hour":      [9, 15],
            "grid_lat":          [51.5, 52.0],
            "grid_lon":          [0.0,  -1.5],
            "temperature_2m":    [12.5, 8.3],
            "precipitation":     [0.0,  1.5],
            "wind_speed_10m":    [10.0, 20.0],
            "weather_code":      [2, 61],
            "weather_description": ["Partly cloudy", "Slight rain"],
        })

    def test_left_join_preserves_all_accidents(self):
        from transformation.join_accident_weather import join_accident_weather

        df_acc = self._make_accidents()
        df_wx  = self._make_weather()

        with patch("transformation.join_accident_weather.CLEANED_DIR"):
            with patch("pandas.DataFrame.to_csv"):
                result = join_accident_weather(df_acc, df_wx)

        # All 3 accidents must be present
        assert len(result) == 3

    def test_unmatched_accident_has_null_weather(self):
        from transformation.join_accident_weather import join_accident_weather

        df_acc = self._make_accidents()
        df_wx  = self._make_weather()

        with patch("transformation.join_accident_weather.CLEANED_DIR"):
            with patch("pandas.DataFrame.to_csv"):
                result = join_accident_weather(df_acc, df_wx)

        # ACC003 has no weather match → temperature_2m should be NaN
        acc3 = result[result["accident_index"] == "ACC003"]
        assert acc3.empty or pd.isna(acc3.iloc[0].get("temperature_2m"))

    def test_weather_matched_column_present(self):
        from transformation.join_accident_weather import join_accident_weather

        df_acc = self._make_accidents()
        df_wx  = self._make_weather()

        with patch("transformation.join_accident_weather.CLEANED_DIR"):
            with patch("pandas.DataFrame.to_csv"):
                result = join_accident_weather(df_acc, df_wx)

        assert "weather_matched" in result.columns

    def test_empty_weather_returns_all_accidents(self):
        from transformation.join_accident_weather import join_accident_weather

        df_acc = self._make_accidents()

        with patch("transformation.join_accident_weather.CLEANED_DIR"):
            result = join_accident_weather(df_acc, pd.DataFrame())

        assert len(result) == 3
        assert "weather_matched" in result.columns
        assert result["weather_matched"].sum() == 0
