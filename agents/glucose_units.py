"""
Glucose unit configuration and conversion utilities.

Supports both mmol/L and mg/dL formats throughout the application.
The format is determined by GLUCOSE_UNIT environment variable.
"""

import os
from typing import Literal

# Conversion factor
MMOL_TO_MGDL = 18.0182

# Get configured glucose unit from environment
GLUCOSE_UNIT: Literal["mmol/L", "mg/dL"] = os.getenv("GLUCOSE_UNIT", "mmol/L").strip()

if GLUCOSE_UNIT not in ("mmol/L", "mg/dL"):
    raise ValueError(f"Invalid GLUCOSE_UNIT: {GLUCOSE_UNIT}. Must be 'mmol/L' or 'mg/dL'")


# Thresholds in BOTH formats for validation and calculations
THRESHOLDS_MGDL = {
    "target_low": 70,
    "target_high": 180,
    "hypo_threshold": 70,
    "hyper_threshold": 180,
    "severe_hyper_threshold": 250,
}

THRESHOLDS_MMOL = {
    "target_low": 3.9,
    "target_high": 10.0,
    "hypo_threshold": 3.9,
    "hyper_threshold": 10.0,
    "severe_hyper_threshold": 13.9,
}

# Get thresholds in configured unit
THRESHOLDS = THRESHOLDS_MMOL if GLUCOSE_UNIT == "mmol/L" else THRESHOLDS_MGDL


def to_mgdl(value_mmol: float) -> float:
    """Convert mmol/L to mg/dL."""
    return value_mmol * MMOL_TO_MGDL


def to_mmol(value_mgdl: float) -> float:
    """Convert mg/dL to mmol/L."""
    return value_mgdl / MMOL_TO_MGDL


def convert_to_configured_unit(value_mgdl: float) -> float:
    """Convert mg/dL value to configured glucose unit."""
    if GLUCOSE_UNIT == "mmol/L":
        return round(to_mmol(value_mgdl), 1)
    return round(value_mgdl, 1)


def convert_from_configured_unit(value: float) -> float:
    """Convert from configured glucose unit to mg/dL."""
    if GLUCOSE_UNIT == "mmol/L":
        return to_mgdl(value)
    return value


def format_glucose(value_mgdl: float) -> str:
    """Format glucose value with unit label."""
    converted = convert_to_configured_unit(value_mgdl)
    return f"{converted} {GLUCOSE_UNIT}"


def validate_glucose_range(value_mgdl: float) -> bool:
    """Check if glucose value is in physiologically valid range (in mg/dL)."""
    return 20 <= value_mgdl <= 600
