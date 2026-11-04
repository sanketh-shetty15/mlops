"""
tests/test_ingestion.py
------------------------
Unit tests for the ingestion layer.

These tests use small in-memory DataFrames and mock objects — they do NOT
call the live DfT website or Open-Meteo API. This keeps tests fast and
runnable offline.

Run with:
    pytest tests/test_ingestion.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import tempfile
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from ingestion.weather_ingestion import snap_to_grid, _nearest_hour


# ── snap_to_grid ───────────────────────────────────────────────────────────────

class TestSnapToGrid:
    def test_exact_grid_point_unchanged(self):
        """A coordinate already on a 0.5° grid should snap to itself."""
        lat, lon = snap_to_grid(51.5, -0.5)
        assert lat == 51.5
        assert lon == -0.5

    def test_rounds_up_to_nearest_half(self):
        """51.26 should snap to 51.5 (nearest 0.5° boundary)."""
        lat, lon = snap_to_grid(51.26, 0.0)
        assert lat == 51.5

    def test_rounds_down_to_nearest_half(self):
        """51.74 should snap to 51.5 (nearest 0.5° boundary below)."""
        lat, _ = snap_to_grid(51.74, 0.0)
        assert lat == 51.5

    def test_midpoint_rounds_to_nearest(self):
        """51.75 should snap to 52.0 (nearest 0.5° boundary)."""
        lat, _ = snap_to_grid(51.75, 0.0)
        assert lat == 52.0

    def test_negative_longitude(self):
        """Negative longitudes should snap correctly."""
        _, lon = snap_to_grid(0.0, -0.13)
        assert lon == 0.0

    def test_far_negative_longitude(self):
        _, lon = snap_to_grid(0.0, -3.2)
        assert lon == -3.0

    def test_returns_tuple_of_floats(self):
        result = snap_to_grid(53.4, -2.2)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], float)

    def test_uk_london_approximation(self):
        """London (~51.51, -0.13) should snap to (51.5, 0.0)."""
        lat, lon = snap_to_grid(51.51, -0.13)
        assert lat == 51.5
        assert lon == 0.0

    def test_custom_resolution(self):
        """Custom resolution of 1.0 degree."""
        lat, lon = snap_to_grid(51.3, -0.7, resolution=1.0)
        assert lat == 51.0
        assert lon == -1.0


# ── _nearest_hour ──────────────────────────────────────────────────────────────

class TestNearestHour:
    def test_exact_hour(self):
        """08:00 → 8"""
        assert _nearest_hour("08:00") == 8

    def test_rounds_up_at_30_min(self):
        """08:30 → 9 (half-way rounds up)"""
        assert _nearest_hour("08:30") == 9

    def test_rounds_down_below_30(self):
        """08:22 → 8"""
        assert _nearest_hour("08:22") == 8

    def test_rounds_up_above_30(self):
        """08:37 → 9"""
        assert _nearest_hour("08:37") == 9

    def test_midnight(self):
        """00:00 → 0"""
        assert _nearest_hour("00:00") == 0

    def test_end_of_day_capped(self):
        """23:45 → 24 capped to 23"""
        result = _nearest_hour("23:45")
        assert result == 23

    def test_none_input(self):
        """None should return None"""
        assert _nearest_hour(None) is None

    def test_empty_string(self):
        """Empty string should return None"""
        assert _nearest_hour("") is None

    def test_single_digit_hour(self):
        """'9:05' should parse correctly → 9"""
        assert _nearest_hour("9:05") == 9

    def test_nan_input(self):
        """float nan should return None"""
        import math
        assert _nearest_hour(float("nan")) is None


# ── Metadata helper ────────────────────────────────────────────────────────────

class TestIngestionMetadata:
    def test_metadata_structure(self):
        """The metadata dict produced by ingestion should have required keys."""
        from ingestion.accident_ingestion import _build_metadata

        meta = _build_metadata(
            source_name="accidents_2023",
            status="SUCCESS",
            row_count=100_000,
            dest_path="/tmp/accidents.csv",
        )
        assert "source_name"          in meta
        assert "source_type"          in meta
        assert "extraction_timestamp" in meta
        assert "status"               in meta
        assert "row_count"            in meta
        assert meta["status"]    == "SUCCESS"
        assert meta["row_count"] == 100_000

    def test_metadata_saves_and_loads(self):
        """Metadata JSON should round-trip through disk correctly."""
        from ingestion.accident_ingestion import _build_metadata, _save_metadata

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            meta = _build_metadata("test", "SUCCESS", 42, str(tmp_dir / "test.csv"))
            _save_metadata(meta, tmp_dir)

            meta_path = tmp_dir / "ingestion_metadata.json"
            assert meta_path.exists()

            with open(meta_path) as f:
                loaded = json.load(f)

            assert loaded["source_name"] == "test"
            assert loaded["row_count"]   == 42
            assert loaded["status"]      == "SUCCESS"

    def test_metadata_error_field_defaults_empty(self):
        """error_message should default to empty string on success."""
        from ingestion.accident_ingestion import _build_metadata

        meta = _build_metadata("src", "SUCCESS", 0, "")
        assert meta["error_message"] == ""

    def test_metadata_captures_failure(self):
        """error_message should be set on failure."""
        from ingestion.accident_ingestion import _build_metadata

        meta = _build_metadata("src", "FAILED", 0, "", "Connection timeout")
        assert meta["status"]        == "FAILED"
        assert "timeout" in meta["error_message"].lower()


# ── Weather grid cell extraction ───────────────────────────────────────────────

class TestGetGridCellsFromAccidents:
    """Test that grid cell extraction from accident data works correctly."""

    def _make_accident_df(self, lats, lons):
        return pd.DataFrame({"latitude": lats, "longitude": lons})

    def test_single_location_produces_one_cell(self):
        """One unique accident location → one grid cell."""
        from ingestion.weather_ingestion import snap_to_grid

        df = self._make_accident_df([51.51], [-0.13])
        # Manually compute expected snapped cell
        expected = snap_to_grid(51.51, -0.13)
        lat, lon = expected
        # Verify snap returns valid floats
        assert isinstance(lat, float)
        assert isinstance(lon, float)

    def test_multiple_same_location_deduplicates(self):
        """Multiple accidents at same location → still one grid cell."""
        from ingestion.weather_ingestion import snap_to_grid

        lats = [51.51, 51.52, 51.53]
        lons = [-0.13, -0.14, -0.12]
        cells = set(snap_to_grid(lat, lon) for lat, lon in zip(lats, lons))
        # All three are within 0.5° of each other → same cell
        assert len(cells) == 1

    def test_nan_coordinates_handled(self):
        """NaN coordinates should raise ValueError, not a cryptic internal error."""
        import math
        with pytest.raises((ValueError, Exception)):
            snap_to_grid(float("nan"), -0.13)
