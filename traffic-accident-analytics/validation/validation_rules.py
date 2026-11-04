"""
validation/validation_rules.py
--------------------------------
Defines every data-quality rule as a self-contained callable.

Each rule function takes a pd.DataFrame and returns a RuleResult
named-tuple containing:
    - rule_name   : str
    - passed      : bool
    - message     : str
    - failed_count: int    (rows that violated the rule)
    - total_count : int    (rows evaluated)

Rules are organised into:
    ACCIDENT_RULES   - applied to the cleaned accident DataFrame
    VEHICLE_RULES    - applied to the cleaned vehicle DataFrame
    CASUALTY_RULES   - applied to the cleaned casualty DataFrame
    WEATHER_RULES    - applied to the cleaned weather DataFrame

Each rule also defines what should happen on failure:
    - REJECT   : the row must be moved to the rejected dataset
    - LOG_WARN : the row may remain but the anomaly is logged
    - FAIL_PIPELINE : the whole pipeline should halt (catastrophic failure)

These actions are used by data_quality.py when running the full report.
"""

from dataclasses import dataclass, field
from typing import Callable, List
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    LAT_MIN, LAT_MAX, LON_MIN, LON_MAX,
    VALID_SEVERITIES,
)


# ── Result container ───────────────────────────────────────────────────────────

@dataclass
class RuleResult:
    rule_name:    str
    passed:       bool
    message:      str
    failed_count: int = 0
    total_count:  int = 0
    action:       str = "REJECT"      # REJECT | LOG_WARN | FAIL_PIPELINE

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        pct = (
            f" ({100 * self.failed_count / self.total_count:.1f}% failed)"
            if self.total_count and not self.passed else ""
        )
        return (
            f"[{status}] {self.rule_name}: {self.message}"
            f" — {self.failed_count}/{self.total_count} rows{pct}"
        )


@dataclass
class ValidationRule:
    """A named rule with its check function and failure action."""
    name:    str
    check:   Callable[[pd.DataFrame], RuleResult]
    action:  str = "REJECT"          # what to do when this rule fails


# ── Accident rules ─────────────────────────────────────────────────────────────

def rule_accident_row_count(df: pd.DataFrame) -> RuleResult:
    """Pipeline-level sanity: the cleaned dataset must be non-empty."""
    passed = len(df) > 0
    return RuleResult(
        rule_name="accident_row_count",
        passed=passed,
        message=f"Dataset contains {len(df):,} rows" if passed else "Dataset is EMPTY",
        failed_count=0 if passed else 1,
        total_count=1,
        action="FAIL_PIPELINE",
    )


def rule_accident_id_not_null(df: pd.DataFrame) -> RuleResult:
    """Every row must have a non-null, non-empty accident_index."""
    col = "accident_index"
    if col not in df.columns:
        return RuleResult(rule_name="accident_id_not_null", passed=False,
                          message="Column 'accident_index' missing from dataset",
                          failed_count=1, total_count=1, action="FAIL_PIPELINE")
    bad = df[col].isna() | (df[col].astype(str).str.strip() == "") | (df[col].astype(str) == "nan")
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="accident_id_not_null",
        passed=(n_bad == 0),
        message="All accident_index values present" if n_bad == 0
                else f"{n_bad:,} rows have null/empty accident_index",
        failed_count=n_bad,
        total_count=len(df),
        action="REJECT",
    )


def rule_no_duplicate_accident_index(df: pd.DataFrame) -> RuleResult:
    """accident_index must be unique across the dataset."""
    col = "accident_index"
    if col not in df.columns:
        return RuleResult(rule_name="no_duplicate_accident_index", passed=False,
                          message="Column missing", failed_count=1, total_count=1,
                          action="FAIL_PIPELINE")
    n_dups = int(df.duplicated(subset=[col]).sum())
    return RuleResult(
        rule_name="no_duplicate_accident_index",
        passed=(n_dups == 0),
        message="No duplicates found" if n_dups == 0
                else f"{n_dups:,} duplicate accident_index values",
        failed_count=n_dups,
        total_count=len(df),
        action="REJECT",
    )


def rule_latitude_range(df: pd.DataFrame) -> RuleResult:
    """Latitude must be between -90 and 90."""
    col = "latitude"
    if col not in df.columns:
        return RuleResult(rule_name="latitude_range", passed=False,
                          message="Column 'latitude' missing",
                          failed_count=1, total_count=1, action="REJECT")
    bad = df[col].isna() | (df[col] < LAT_MIN) | (df[col] > LAT_MAX)
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="latitude_range",
        passed=(n_bad == 0),
        message=f"All latitudes in [{LAT_MIN}, {LAT_MAX}]" if n_bad == 0
                else f"{n_bad:,} rows have invalid latitude",
        failed_count=n_bad,
        total_count=len(df),
        action="REJECT",
    )


def rule_longitude_range(df: pd.DataFrame) -> RuleResult:
    """Longitude must be between -180 and 180."""
    col = "longitude"
    if col not in df.columns:
        return RuleResult(rule_name="longitude_range", passed=False,
                          message="Column 'longitude' missing",
                          failed_count=1, total_count=1, action="REJECT")
    bad = df[col].isna() | (df[col] < LON_MIN) | (df[col] > LON_MAX)
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="longitude_range",
        passed=(n_bad == 0),
        message=f"All longitudes in [{LON_MIN}, {LON_MAX}]" if n_bad == 0
                else f"{n_bad:,} rows have invalid longitude",
        failed_count=n_bad,
        total_count=len(df),
        action="REJECT",
    )


def rule_accident_date_valid(df: pd.DataFrame) -> RuleResult:
    """accident_date must be parseable and not null."""
    col = "accident_date"
    if col not in df.columns:
        return RuleResult(rule_name="accident_date_valid", passed=False,
                          message="Column 'accident_date' missing",
                          failed_count=1, total_count=1, action="REJECT")
    dates = pd.to_datetime(df[col], errors="coerce")
    n_bad = int(dates.isna().sum())
    return RuleResult(
        rule_name="accident_date_valid",
        passed=(n_bad == 0),
        message="All dates are valid" if n_bad == 0
                else f"{n_bad:,} rows have invalid/missing date",
        failed_count=n_bad,
        total_count=len(df),
        action="REJECT",
    )


def rule_accident_time_format(df: pd.DataFrame) -> RuleResult:
    """
    accident_time should follow HH:MM format.
    Rows with malformed time are warned (not rejected) because
    the accident itself is still useful without an exact time.
    """
    col = "accident_time"
    if col not in df.columns:
        return RuleResult(rule_name="accident_time_format", passed=True,
                          message="Column 'accident_time' not present (non-critical)",
                          action="LOG_WARN")
    import re
    pattern = re.compile(r"^\d{1,2}:\d{2}$")
    bad = df[col].apply(
        lambda v: not (isinstance(v, str) and pattern.match(v.strip()))
    )
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="accident_time_format",
        passed=(n_bad == 0),
        message="All times in HH:MM format" if n_bad == 0
                else f"{n_bad:,} rows have malformed or missing time",
        failed_count=n_bad,
        total_count=len(df),
        action="LOG_WARN",   # time missing is non-fatal for accident validity
    )


def rule_severity_valid(df: pd.DataFrame) -> RuleResult:
    """accident_severity must be 1 (Fatal), 2 (Serious) or 3 (Slight)."""
    col = "accident_severity"
    if col not in df.columns:
        return RuleResult(rule_name="severity_valid", passed=False,
                          message="Column 'accident_severity' missing",
                          failed_count=1, total_count=1, action="REJECT")
    bad = df[col].isna() | ~df[col].isin(VALID_SEVERITIES)
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="severity_valid",
        passed=(n_bad == 0),
        message=f"All severity values in {VALID_SEVERITIES}" if n_bad == 0
                else f"{n_bad:,} rows have invalid/missing severity",
        failed_count=n_bad,
        total_count=len(df),
        action="REJECT",
    )


def rule_vehicle_count_positive(df: pd.DataFrame) -> RuleResult:
    """number_of_vehicles must be >= 1 (no accident with 0 vehicles)."""
    col = "number_of_vehicles"
    if col not in df.columns:
        return RuleResult(rule_name="vehicle_count_positive", passed=True,
                          message="Column not present — skipped",
                          action="LOG_WARN")
    bad = df[col].notna() & (df[col] < 1)
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="vehicle_count_positive",
        passed=(n_bad == 0),
        message="All vehicle counts >= 1" if n_bad == 0
                else f"{n_bad:,} rows have vehicle_count < 1",
        failed_count=n_bad,
        total_count=int(df[col].notna().sum()),
        action="LOG_WARN",  # rare data error — warn but don't reject
    )


def rule_casualty_count_non_negative(df: pd.DataFrame) -> RuleResult:
    """number_of_casualties must be >= 0."""
    col = "number_of_casualties"
    if col not in df.columns:
        return RuleResult(rule_name="casualty_count_non_negative", passed=True,
                          message="Column not present — skipped", action="LOG_WARN")
    bad = df[col].notna() & (df[col] < 0)
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="casualty_count_non_negative",
        passed=(n_bad == 0),
        message="All casualty counts >= 0" if n_bad == 0
                else f"{n_bad:,} rows have negative casualty count",
        failed_count=n_bad,
        total_count=int(df[col].notna().sum()),
        action="REJECT",
    )


def rule_uk_bounding_box(df: pd.DataFrame) -> RuleResult:
    """
    Soft check: UK accidents should be within the UK bounding box.
    Rows outside are warned (not rejected) because some offshore or
    Channel Island records legitimately appear outside this box.
    """
    from config.config import UK_LAT_MIN, UK_LAT_MAX, UK_LON_MIN, UK_LON_MAX
    if "latitude" not in df.columns or "longitude" not in df.columns:
        return RuleResult(rule_name="uk_bounding_box", passed=True,
                          message="Coordinates not present — skipped", action="LOG_WARN")
    outside = (
        (df["latitude"]  < UK_LAT_MIN) | (df["latitude"]  > UK_LAT_MAX) |
        (df["longitude"] < UK_LON_MIN) | (df["longitude"] > UK_LON_MAX)
    )
    n_out = int(outside.sum())
    return RuleResult(
        rule_name="uk_bounding_box",
        passed=(n_out == 0),
        message="All accidents within UK bounding box" if n_out == 0
                else f"{n_out:,} accidents outside expected UK bounding box (warn only)",
        failed_count=n_out,
        total_count=len(df),
        action="LOG_WARN",
    )


# ── Vehicle rules ──────────────────────────────────────────────────────────────

def rule_vehicle_accident_index_not_null(df: pd.DataFrame) -> RuleResult:
    col = "accident_index"
    if col not in df.columns:
        return RuleResult(rule_name="vehicle_accident_index_not_null", passed=False,
                          message="Column missing", action="FAIL_PIPELINE")
    bad = df[col].isna() | (df[col].astype(str) == "nan")
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="vehicle_accident_index_not_null",
        passed=(n_bad == 0),
        message="All vehicle rows have accident_index" if n_bad == 0
                else f"{n_bad:,} vehicle rows missing accident_index",
        failed_count=n_bad, total_count=len(df), action="REJECT",
    )


def rule_vehicle_no_duplicates(df: pd.DataFrame) -> RuleResult:
    cols = [c for c in ["accident_index", "vehicle_reference"] if c in df.columns]
    if len(cols) < 2:
        return RuleResult(rule_name="vehicle_no_duplicates", passed=True,
                          message="Key columns not present — skipped", action="LOG_WARN")
    n_dups = int(df.duplicated(subset=cols).sum())
    return RuleResult(
        rule_name="vehicle_no_duplicates",
        passed=(n_dups == 0),
        message="No duplicate vehicle records" if n_dups == 0
                else f"{n_dups:,} duplicate vehicle records",
        failed_count=n_dups, total_count=len(df), action="REJECT",
    )


# ── Casualty rules ─────────────────────────────────────────────────────────────

def rule_casualty_accident_index_not_null(df: pd.DataFrame) -> RuleResult:
    col = "accident_index"
    if col not in df.columns:
        return RuleResult(rule_name="casualty_accident_index_not_null", passed=False,
                          message="Column missing", action="FAIL_PIPELINE")
    bad = df[col].isna() | (df[col].astype(str) == "nan")
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="casualty_accident_index_not_null",
        passed=(n_bad == 0),
        message="All casualty rows have accident_index" if n_bad == 0
                else f"{n_bad:,} casualty rows missing accident_index",
        failed_count=n_bad, total_count=len(df), action="REJECT",
    )


def rule_casualty_severity_valid(df: pd.DataFrame) -> RuleResult:
    col = "casualty_severity"
    if col not in df.columns:
        return RuleResult(rule_name="casualty_severity_valid", passed=True,
                          message="Column not present — skipped", action="LOG_WARN")
    bad = df[col].notna() & ~df[col].isin(VALID_SEVERITIES)
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="casualty_severity_valid",
        passed=(n_bad == 0),
        message="All casualty severities valid" if n_bad == 0
                else f"{n_bad:,} casualty rows with invalid severity",
        failed_count=n_bad, total_count=len(df), action="REJECT",
    )


# ── Weather rules ──────────────────────────────────────────────────────────────

def rule_weather_row_count(df: pd.DataFrame) -> RuleResult:
    passed = len(df) > 0
    return RuleResult(
        rule_name="weather_row_count",
        passed=passed,
        message=f"Weather dataset has {len(df):,} rows" if passed else "Weather dataset is EMPTY",
        failed_count=0 if passed else 1, total_count=1,
        action="LOG_WARN",   # missing weather is non-fatal
    )


def rule_weather_datetime_not_null(df: pd.DataFrame) -> RuleResult:
    col = "datetime"
    if col not in df.columns:
        return RuleResult(rule_name="weather_datetime_not_null", passed=False,
                          message="Column 'datetime' missing", action="LOG_WARN")
    bad = df[col].isna()
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="weather_datetime_not_null",
        passed=(n_bad == 0),
        message="All weather rows have datetime" if n_bad == 0
                else f"{n_bad:,} weather rows missing datetime",
        failed_count=n_bad, total_count=len(df), action="LOG_WARN",
    )


def rule_weather_temperature_plausible(df: pd.DataFrame) -> RuleResult:
    """Temperature_2m should be within a plausible range for the UK (-30°C to 45°C)."""
    col = "temperature_2m"
    if col not in df.columns:
        return RuleResult(rule_name="weather_temperature_plausible", passed=True,
                          message="Column not present — skipped", action="LOG_WARN")
    bad = df[col].notna() & ((df[col] < -30) | (df[col] > 45))
    n_bad = int(bad.sum())
    return RuleResult(
        rule_name="weather_temperature_plausible",
        passed=(n_bad == 0),
        message="All temperatures in plausible range" if n_bad == 0
                else f"{n_bad:,} rows have implausible temperature",
        failed_count=n_bad, total_count=len(df), action="LOG_WARN",
    )


# ── Rule sets by dataset ───────────────────────────────────────────────────────

ACCIDENT_RULES: List[ValidationRule] = [
    ValidationRule("accident_row_count",            rule_accident_row_count,            "FAIL_PIPELINE"),
    ValidationRule("accident_id_not_null",          rule_accident_id_not_null,          "REJECT"),
    ValidationRule("no_duplicate_accident_index",   rule_no_duplicate_accident_index,   "REJECT"),
    ValidationRule("latitude_range",                rule_latitude_range,                "REJECT"),
    ValidationRule("longitude_range",               rule_longitude_range,               "REJECT"),
    ValidationRule("accident_date_valid",           rule_accident_date_valid,           "REJECT"),
    ValidationRule("accident_time_format",          rule_accident_time_format,          "LOG_WARN"),
    ValidationRule("severity_valid",                rule_severity_valid,                "REJECT"),
    ValidationRule("vehicle_count_positive",        rule_vehicle_count_positive,        "LOG_WARN"),
    ValidationRule("casualty_count_non_negative",   rule_casualty_count_non_negative,   "REJECT"),
    ValidationRule("uk_bounding_box",               rule_uk_bounding_box,               "LOG_WARN"),
]

VEHICLE_RULES: List[ValidationRule] = [
    ValidationRule("vehicle_accident_index_not_null", rule_vehicle_accident_index_not_null, "REJECT"),
    ValidationRule("vehicle_no_duplicates",           rule_vehicle_no_duplicates,            "REJECT"),
]

CASUALTY_RULES: List[ValidationRule] = [
    ValidationRule("casualty_accident_index_not_null", rule_casualty_accident_index_not_null, "REJECT"),
    ValidationRule("casualty_severity_valid",           rule_casualty_severity_valid,           "REJECT"),
]

WEATHER_RULES: List[ValidationRule] = [
    ValidationRule("weather_row_count",              rule_weather_row_count,              "LOG_WARN"),
    ValidationRule("weather_datetime_not_null",      rule_weather_datetime_not_null,      "LOG_WARN"),
    ValidationRule("weather_temperature_plausible",  rule_weather_temperature_plausible,  "LOG_WARN"),
]
