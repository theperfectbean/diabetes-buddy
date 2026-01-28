"""
Glooko Data Ingestion Module for Diabetes Buddy

Parses Glooko CSV exports and provides comprehensive data analysis
for blood glucose, insulin, carbohydrates, and exercise data.

Safety: All outputs pass through SafetyAuditor before user display.
"""

import hashlib
import json
import logging
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from .safety import SafetyAuditor, AuditResult

logger = logging.getLogger(__name__)

# Constants
CACHE_DIR = Path("data/cache")
TARGET_LOW = 70  # mg/dL
TARGET_HIGH = 180  # mg/dL
HYPO_THRESHOLD = 70  # mg/dL
HYPER_THRESHOLD = 180  # mg/dL
SEVERE_HYPER_THRESHOLD = 250  # mg/dL

# Unit conversion
MMOL_TO_MGDL = 18.0182  # Conversion factor from mmol/L to mg/dL

# Dawn phenomenon analysis window (3am-8am)
DAWN_START_HOUR = 3
DAWN_END_HOUR = 8

# Post-meal spike window (1-3 hours after carbs)
POST_MEAL_START_HOURS = 1
POST_MEAL_END_HOURS = 3

# Mandatory disclaimer for all analysis outputs
ANALYSIS_DISCLAIMER = (
    "Data analysis for educational purposes. "
    "Discuss findings with your healthcare team."
)


@dataclass
class CGMReading:
    """A single CGM glucose reading."""
    timestamp: datetime
    glucose_mg_dl: float
    device: Optional[str] = None


@dataclass
class InsulinRecord:
    """An insulin delivery record (basal or bolus)."""
    timestamp: datetime
    units: float
    insulin_type: str  # 'basal' or 'bolus'
    notes: Optional[str] = None


@dataclass
class CarbRecord:
    """A carbohydrate intake record."""
    timestamp: datetime
    grams: float
    meal_type: Optional[str] = None  # breakfast, lunch, dinner, snack
    notes: Optional[str] = None


@dataclass
class ExerciseRecord:
    """An exercise activity record."""
    timestamp: datetime
    duration_minutes: int
    intensity: Optional[str] = None  # low, medium, high
    activity_type: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class DataAnomaly:
    """A detected data anomaly that may indicate issues."""
    timestamp: datetime
    anomaly_type: str
    description: str
    severity: str  # 'info', 'warning', 'critical'
    value: Optional[float] = None


@dataclass
class ParsedData:
    """Container for all parsed Glooko data."""
    cgm_readings: list[CGMReading] = field(default_factory=list)
    insulin_records: list[InsulinRecord] = field(default_factory=list)
    carb_records: list[CarbRecord] = field(default_factory=list)
    exercise_records: list[ExerciseRecord] = field(default_factory=list)
    anomalies: list[DataAnomaly] = field(default_factory=list)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "cgm_count": len(self.cgm_readings),
            "insulin_count": len(self.insulin_records),
            "carb_count": len(self.carb_records),
            "exercise_count": len(self.exercise_records),
            "anomaly_count": len(self.anomalies),
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
        }


class GlookoParser:
    """
    Parser for Glooko diabetes data exports.

    Handles ZIP archives containing CSV files for CGM readings,
    insulin delivery, carbohydrates, and exercise logs.
    """

    # Expected CSV file patterns in Glooko exports
    FILE_PATTERNS = {
        "cgm": ["cgm", "glucose", "bg", "readings"],
        "insulin": ["insulin", "bolus", "basal", "doses"],
        "carbs": ["carb", "food", "meal", "nutrition"],
        "exercise": ["exercise", "activity", "workout"],
    }

    def __init__(self, timezone: str = "UTC"):
        """
        Initialize the parser.

        Args:
            timezone: Target timezone for data conversion (default: UTC)
        """
        self.timezone = timezone
        self._anomalies: list[DataAnomaly] = []

    def load_export(self, file_path: str | Path) -> ParsedData:
        """
        Load and parse a Glooko export file.

        Args:
            file_path: Path to ZIP file or directory containing CSVs

        Returns:
            ParsedData containing all parsed records

        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file format is invalid
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Export file not found: {path}")

        self._anomalies = []

        if path.suffix.lower() == ".zip":
            return self._parse_zip(path)
        elif path.is_dir():
            return self._parse_directory(path)
        elif path.suffix.lower() == ".csv":
            return self._parse_single_csv(path)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

    def _parse_zip(self, zip_path: Path) -> ParsedData:
        """Parse a ZIP archive containing CSV files."""
        parsed = ParsedData()

        with zipfile.ZipFile(zip_path, 'r') as zf:
            csv_files = [f for f in zf.namelist() if f.lower().endswith('.csv')]

            if not csv_files:
                raise ValueError("No CSV files found in ZIP archive")

            for csv_file in csv_files:
                with zf.open(csv_file) as f:
                    content = f.read().decode('utf-8')
                    self._parse_csv_content(csv_file, content, parsed)

        self._finalize_parsed_data(parsed)
        return parsed

    def _parse_directory(self, dir_path: Path) -> ParsedData:
        """Parse all CSV files in a directory."""
        parsed = ParsedData()

        csv_files = list(dir_path.glob("*.csv"))
        if not csv_files:
            raise ValueError(f"No CSV files found in directory: {dir_path}")

        for csv_file in csv_files:
            content = csv_file.read_text(encoding='utf-8')
            self._parse_csv_content(csv_file.name, content, parsed)

        self._finalize_parsed_data(parsed)
        return parsed

    def _parse_single_csv(self, csv_path: Path) -> ParsedData:
        """Parse a single CSV file (auto-detect type)."""
        parsed = ParsedData()
        content = csv_path.read_text(encoding='utf-8')
        self._parse_csv_content(csv_path.name, content, parsed)
        self._finalize_parsed_data(parsed)
        return parsed

    def _parse_csv_content(self, filename: str, content: str, parsed: ParsedData) -> None:
        """Parse CSV content and add to parsed data."""
        filename_lower = filename.lower()

        try:
            # Glooko exports have a metadata row first (Name:..., Date Range:...)
            # Skip it by checking if first row looks like metadata
            lines = content.split('\n')
            skip_rows = 0
            if lines and ':' in lines[0] and 'Name:' in lines[0]:
                skip_rows = 1
                logger.debug(f"Skipping Glooko metadata row in {filename}")

            df = pd.read_csv(StringIO(content), skiprows=skip_rows)

            # Handle BOM character in column names
            df.columns = df.columns.str.replace('\ufeff', '').str.strip()

            # Auto-detect file type based on filename and columns
            file_type = self._detect_file_type(filename_lower, df.columns.tolist())

            if file_type == "cgm":
                self._parse_cgm_data(df, parsed)
            elif file_type == "insulin":
                self._parse_insulin_data(df, parsed, filename=filename)
            elif file_type == "carbs":
                self._parse_carb_data(df, parsed)
            elif file_type == "exercise":
                self._parse_exercise_data(df, parsed)
            else:
                logger.warning(f"Could not determine type for file: {filename}")

        except Exception as e:
            logger.error(f"Error parsing {filename}: {e}")
            self._anomalies.append(DataAnomaly(
                timestamp=datetime.now(),
                anomaly_type="parse_error",
                description=f"Failed to parse {filename}: {str(e)}",
                severity="warning"
            ))

    def _detect_file_type(self, filename: str, columns: list[str]) -> Optional[str]:
        """Detect the type of data in a CSV based on filename and columns."""
        columns_lower = [c.lower() for c in columns]

        # Check filename patterns first
        for file_type, patterns in self.FILE_PATTERNS.items():
            if any(p in filename for p in patterns):
                return file_type

        # Fall back to column detection
        if any(col in columns_lower for col in ["glucose", "bg", "sgv", "cgm"]):
            return "cgm"
        elif any(col in columns_lower for col in ["insulin", "bolus", "basal", "units"]):
            return "insulin"
        elif any(col in columns_lower for col in ["carb", "carbs", "carbohydrate", "grams"]):
            return "carbs"
        elif any(col in columns_lower for col in ["exercise", "activity", "duration"]):
            return "exercise"

        return None

    def _parse_timestamp(self, row: pd.Series, possible_cols: list[str]) -> Optional[datetime]:
        """Parse timestamp from a row, trying multiple possible column names."""
        for col in possible_cols:
            if col in row.index and pd.notna(row[col]):
                try:
                    ts = pd.to_datetime(row[col], utc=True)
                    return ts.to_pydatetime().replace(tzinfo=None)
                except Exception:
                    continue
        return None

    def _parse_cgm_data(self, df: pd.DataFrame, parsed: ParsedData) -> None:
        """Parse CGM glucose readings from DataFrame."""
        timestamp_cols = ["timestamp", "time", "date", "datetime", "created_at",
                         "Timestamp", "Time", "Date"]
        # Glooko-specific columns (mmol/L)
        glucose_mmol_cols = ["CGM Glucose Value (mmol/l)", "Glucose Value (mmol/l)",
                            "glucose_mmol", "mmol/l", "mmol"]
        # Standard columns (mg/dL)
        glucose_mgdl_cols = ["glucose", "bg", "sgv", "value", "glucose_mg_dl",
                            "Glucose", "BG", "Value", "reading", "mg/dl",
                            "CGM Glucose Value (mg/dl)"]
        device_cols = ["Serial Number", "device", "Device", "source"]

        df.columns = df.columns.str.strip()
        logger.debug(f"CGM columns found: {list(df.columns)}")

        for _, row in df.iterrows():
            ts = self._parse_timestamp(row, timestamp_cols)
            if ts is None:
                continue

            glucose = None
            is_mmol = False

            # Try mmol/L columns first (Glooko format)
            for col in glucose_mmol_cols:
                if col in row.index and pd.notna(row[col]):
                    try:
                        glucose = float(row[col])
                        is_mmol = True
                        break
                    except (ValueError, TypeError):
                        continue

            # Fall back to mg/dL columns
            if glucose is None:
                for col in glucose_mgdl_cols:
                    if col in row.index and pd.notna(row[col]):
                        try:
                            glucose = float(row[col])
                            break
                        except (ValueError, TypeError):
                            continue

            if glucose is not None:
                # Convert mmol/L to mg/dL if needed
                if is_mmol:
                    glucose = glucose * MMOL_TO_MGDL

                # Validate glucose value (now in mg/dL)
                if glucose < 20 or glucose > 600:
                    self._anomalies.append(DataAnomaly(
                        timestamp=ts,
                        anomaly_type="invalid_glucose",
                        description=f"Glucose value out of range: {glucose:.1f} mg/dL",
                        severity="warning",
                        value=glucose
                    ))
                    continue

                # Get device info
                device = None
                for col in device_cols:
                    if col in row.index and pd.notna(row[col]):
                        device = str(row[col])
                        break

                parsed.cgm_readings.append(CGMReading(
                    timestamp=ts,
                    glucose_mg_dl=round(glucose, 1),
                    device=device
                ))

    def _parse_insulin_data(self, df: pd.DataFrame, parsed: ParsedData,
                            filename: str = "") -> None:
        """Parse insulin delivery records from DataFrame.

        Also extracts carb records from bolus data if 'Carbs Input (g)' column exists.
        """
        timestamp_cols = ["timestamp", "time", "date", "datetime", "created_at",
                         "Timestamp", "Time", "Date"]
        # Glooko-specific columns
        units_cols = ["Insulin Delivered (U)", "Insulin Value (U)", "Rate (U/h)",
                     "units", "amount", "dose", "value", "Units", "Amount", "Dose"]
        type_cols = ["Insulin Type", "type", "insulin_type", "kind", "Type", "Category"]
        # Carb columns that may be embedded in bolus data
        carb_input_cols = ["Carbs Input (g)", "Carbs (g)", "carbs_input"]

        df.columns = df.columns.str.strip()
        logger.debug(f"Insulin columns found: {list(df.columns)}")

        # Determine default insulin type from filename
        filename_lower = filename.lower()
        default_type = "bolus"
        if "basal" in filename_lower:
            default_type = "basal"

        for _, row in df.iterrows():
            ts = self._parse_timestamp(row, timestamp_cols)
            if ts is None:
                continue

            units = None
            for col in units_cols:
                if col in row.index and pd.notna(row[col]):
                    try:
                        units = float(row[col])
                        break
                    except (ValueError, TypeError):
                        continue

            if units is not None and units > 0:
                # Validate insulin units
                if units > 100:
                    self._anomalies.append(DataAnomaly(
                        timestamp=ts,
                        anomaly_type="invalid_insulin",
                        description=f"Insulin units out of range: {units}",
                        severity="warning",
                        value=units
                    ))
                    continue

                # Determine insulin type from column or filename
                insulin_type = default_type
                for col in type_cols:
                    if col in row.index and pd.notna(row[col]):
                        type_str = str(row[col]).lower()
                        if "basal" in type_str:
                            insulin_type = "basal"
                        elif any(t in type_str for t in ["bolus", "normal", "correction"]):
                            insulin_type = "bolus"
                        break

                parsed.insulin_records.append(InsulinRecord(
                    timestamp=ts,
                    units=units,
                    insulin_type=insulin_type,
                    notes=row.get("notes", row.get("Notes"))
                ))

            # Also extract carb data from bolus records if present
            for carb_col in carb_input_cols:
                if carb_col in row.index and pd.notna(row[carb_col]):
                    try:
                        carbs = float(row[carb_col])
                        if carbs > 0:
                            parsed.carb_records.append(CarbRecord(
                                timestamp=ts,
                                grams=carbs,
                                meal_type=None,
                                notes="From bolus wizard"
                            ))
                    except (ValueError, TypeError):
                        pass
                    break

    def _parse_carb_data(self, df: pd.DataFrame, parsed: ParsedData) -> None:
        """Parse carbohydrate intake records from DataFrame."""
        timestamp_cols = ["timestamp", "time", "date", "datetime", "created_at",
                         "Timestamp", "Time", "Date"]
        # Glooko-specific columns
        carb_cols = ["Carbs (g)", "Carbs Input (g)", "Carbohydrates (g)",
                    "carbs", "carbohydrates", "grams", "carb", "amount",
                    "Carbs", "Carbohydrates", "Grams"]

        df.columns = df.columns.str.strip()
        logger.debug(f"Carbs columns found: {list(df.columns)}")

        for _, row in df.iterrows():
            ts = self._parse_timestamp(row, timestamp_cols)
            if ts is None:
                continue

            grams = None
            for col in carb_cols:
                if col in row.index and pd.notna(row[col]):
                    try:
                        grams = float(row[col])
                        break
                    except (ValueError, TypeError):
                        continue

            if grams is not None:
                # Validate carb value
                if grams < 0 or grams > 500:
                    self._anomalies.append(DataAnomaly(
                        timestamp=ts,
                        anomaly_type="invalid_carbs",
                        description=f"Carb value out of range: {grams}g",
                        severity="warning",
                        value=grams
                    ))
                    continue

                parsed.carb_records.append(CarbRecord(
                    timestamp=ts,
                    grams=grams,
                    meal_type=row.get("meal_type", row.get("Meal")),
                    notes=row.get("notes", row.get("Notes"))
                ))

    def _parse_exercise_data(self, df: pd.DataFrame, parsed: ParsedData) -> None:
        """Parse exercise activity records from DataFrame."""
        timestamp_cols = ["timestamp", "time", "date", "datetime", "start_time",
                         "Timestamp", "Time", "Date"]
        # Glooko-specific columns
        duration_cols = ["Duration (minutes)", "duration", "minutes", "duration_minutes",
                        "length", "Duration", "Minutes"]

        df.columns = df.columns.str.strip()
        logger.debug(f"Exercise columns found: {list(df.columns)}")

        for _, row in df.iterrows():
            ts = self._parse_timestamp(row, timestamp_cols)
            if ts is None:
                continue

            duration = None
            for col in duration_cols:
                if col in row.index and pd.notna(row[col]):
                    try:
                        duration = int(float(row[col]))
                        break
                    except (ValueError, TypeError):
                        continue

            if duration is not None and duration > 0:
                parsed.exercise_records.append(ExerciseRecord(
                    timestamp=ts,
                    duration_minutes=duration,
                    intensity=row.get("intensity", row.get("Intensity")),
                    activity_type=row.get("activity", row.get("Activity", row.get("type"))),
                    notes=row.get("notes", row.get("Notes"))
                ))

    def _finalize_parsed_data(self, parsed: ParsedData) -> None:
        """Finalize parsed data with date range and anomalies."""
        # Collect all timestamps
        all_timestamps = []
        all_timestamps.extend([r.timestamp for r in parsed.cgm_readings])
        all_timestamps.extend([r.timestamp for r in parsed.insulin_records])
        all_timestamps.extend([r.timestamp for r in parsed.carb_records])
        all_timestamps.extend([r.timestamp for r in parsed.exercise_records])

        if all_timestamps:
            parsed.start_date = min(all_timestamps)
            parsed.end_date = max(all_timestamps)

        parsed.anomalies = self._anomalies.copy()

        # Check for data gaps
        self._detect_data_gaps(parsed)

    def _detect_data_gaps(self, parsed: ParsedData) -> None:
        """Detect significant gaps in CGM data."""
        if len(parsed.cgm_readings) < 2:
            return

        sorted_readings = sorted(parsed.cgm_readings, key=lambda r: r.timestamp)

        for i in range(1, len(sorted_readings)):
            gap = sorted_readings[i].timestamp - sorted_readings[i-1].timestamp

            # Flag gaps longer than 3 hours
            if gap > timedelta(hours=3):
                parsed.anomalies.append(DataAnomaly(
                    timestamp=sorted_readings[i-1].timestamp,
                    anomaly_type="data_gap",
                    description=f"CGM data gap of {gap.total_seconds() / 3600:.1f} hours",
                    severity="info"
                ))


class DataAnalyzer:
    """
    Analyzer for diabetes data patterns and trends.

    Provides time-in-range calculations, pattern detection,
    and contextual analysis of glucose data.
    """

    def __init__(self):
        """Initialize the analyzer."""
        pass

    def calculate_time_in_range(self, readings: list[CGMReading]) -> dict:
        """
        Calculate time-in-range statistics for glucose readings.

        Args:
            readings: List of CGM readings

        Returns:
            Dictionary with TIR percentages for different thresholds
        """
        if not readings:
            return {
                "total_readings": 0,
                "time_in_range_70_180": 0.0,
                "time_below_70": 0.0,
                "time_above_180": 0.0,
                "time_above_250": 0.0,
                "average_glucose": 0.0,
                "glucose_std": 0.0,
                "coefficient_of_variation": 0.0,
                "estimated_a1c": 0.0,
            }

        glucose_values = np.array([r.glucose_mg_dl for r in readings])
        total = len(glucose_values)

        in_range = np.sum((glucose_values >= TARGET_LOW) & (glucose_values <= TARGET_HIGH))
        below_70 = np.sum(glucose_values < HYPO_THRESHOLD)
        above_180 = np.sum(glucose_values > HYPER_THRESHOLD)
        above_250 = np.sum(glucose_values > SEVERE_HYPER_THRESHOLD)

        avg_glucose = np.mean(glucose_values)
        std_glucose = np.std(glucose_values)
        cv = (std_glucose / avg_glucose * 100) if avg_glucose > 0 else 0

        # Estimated A1C using ADAG formula: A1C = (avg_glucose + 46.7) / 28.7
        estimated_a1c = (avg_glucose + 46.7) / 28.7

        return {
            "total_readings": total,
            "time_in_range_70_180": round(in_range / total * 100, 1),
            "time_below_70": round(below_70 / total * 100, 1),
            "time_above_180": round(above_180 / total * 100, 1),
            "time_above_250": round(above_250 / total * 100, 1),
            "average_glucose": round(avg_glucose, 1),
            "glucose_std": round(std_glucose, 1),
            "coefficient_of_variation": round(cv, 1),
            "estimated_a1c": round(estimated_a1c, 1),
        }

    def detect_dawn_phenomenon(self, readings: list[CGMReading]) -> dict:
        """
        Detect dawn phenomenon by analyzing 3am-8am glucose trends.

        The dawn phenomenon is characterized by rising glucose levels
        in the early morning hours due to hormonal changes.

        Args:
            readings: List of CGM readings

        Returns:
            Dictionary with dawn phenomenon analysis
        """
        if not readings:
            return {"detected": False, "evidence": [], "confidence": 0.0}

        # Group readings by date and filter to dawn hours
        dawn_data = {}

        for reading in readings:
            hour = reading.timestamp.hour
            if DAWN_START_HOUR <= hour < DAWN_END_HOUR:
                date_key = reading.timestamp.date()
                if date_key not in dawn_data:
                    dawn_data[date_key] = []
                dawn_data[date_key].append(reading)

        if len(dawn_data) < 3:
            return {
                "detected": False,
                "evidence": ["Insufficient data for dawn phenomenon analysis"],
                "confidence": 0.0,
                "days_analyzed": len(dawn_data)
            }

        # Analyze each day for rising trend
        rising_days = 0
        rise_magnitudes = []
        evidence = []

        for date, day_readings in dawn_data.items():
            sorted_readings = sorted(day_readings, key=lambda r: r.timestamp)

            if len(sorted_readings) < 4:
                continue

            # Calculate trend using linear regression
            times = [(r.timestamp - sorted_readings[0].timestamp).total_seconds() / 3600
                    for r in sorted_readings]
            values = [r.glucose_mg_dl for r in sorted_readings]

            if len(times) >= 2:
                slope, _, r_value, _, _ = stats.linregress(times, values)

                # Rising trend: slope > 5 mg/dL per hour with reasonable fit
                if slope > 5 and r_value**2 > 0.3:
                    rising_days += 1
                    rise_magnitudes.append(slope)

        total_days = len([d for d in dawn_data.values() if len(d) >= 4])

        if total_days == 0:
            return {
                "detected": False,
                "evidence": ["Insufficient readings during dawn hours"],
                "confidence": 0.0,
                "days_analyzed": 0
            }

        detection_rate = rising_days / total_days
        avg_rise = np.mean(rise_magnitudes) if rise_magnitudes else 0

        detected = detection_rate >= 0.5 and avg_rise > 10

        if detected:
            evidence.append(
                f"Rising glucose trend detected on {rising_days} of {total_days} days "
                f"({detection_rate*100:.0f}%) during 3am-8am window"
            )
            evidence.append(
                f"Average rise rate: {avg_rise:.1f} mg/dL per hour"
            )
        else:
            evidence.append(
                f"No consistent dawn phenomenon pattern found "
                f"({rising_days} of {total_days} days showed rising trend)"
            )

        return {
            "detected": detected,
            "evidence": evidence,
            "confidence": round(detection_rate * 100, 1) if detected else 0.0,
            "days_analyzed": total_days,
            "average_rise_rate": round(avg_rise, 1) if rise_magnitudes else 0.0,
        }

    def detect_post_meal_spikes(
        self,
        readings: list[CGMReading],
        carbs: list[CarbRecord]
    ) -> dict:
        """
        Identify post-meal glucose spikes 1-3 hours after carb entries.

        Args:
            readings: List of CGM readings
            carbs: List of carbohydrate records

        Returns:
            Dictionary with post-meal spike analysis
        """
        if not readings or not carbs:
            return {
                "meals_analyzed": 0,
                "spikes_detected": 0,
                "spike_rate": 0.0,
                "average_spike": 0.0,
                "evidence": ["Insufficient data for post-meal analysis"]
            }

        # Create a lookup structure for glucose readings
        readings_df = pd.DataFrame([
            {"timestamp": r.timestamp, "glucose": r.glucose_mg_dl}
            for r in readings
        ])
        readings_df = readings_df.sort_values("timestamp")

        spikes = []
        meals_analyzed = 0
        evidence = []

        for carb in carbs:
            if carb.grams < 10:  # Skip very small carb entries
                continue

            # Find glucose at meal time
            pre_meal_window = carb.timestamp - timedelta(minutes=15)
            post_meal_start = carb.timestamp + timedelta(hours=POST_MEAL_START_HOURS)
            post_meal_end = carb.timestamp + timedelta(hours=POST_MEAL_END_HOURS)

            # Get pre-meal glucose
            pre_mask = (readings_df["timestamp"] >= pre_meal_window) & \
                       (readings_df["timestamp"] <= carb.timestamp)
            pre_readings = readings_df[pre_mask]

            # Get post-meal glucose (1-3 hours after)
            post_mask = (readings_df["timestamp"] >= post_meal_start) & \
                        (readings_df["timestamp"] <= post_meal_end)
            post_readings = readings_df[post_mask]

            if pre_readings.empty or post_readings.empty:
                continue

            meals_analyzed += 1
            pre_glucose = pre_readings["glucose"].mean()
            post_peak = post_readings["glucose"].max()
            spike_magnitude = post_peak - pre_glucose

            # Spike threshold: >50 mg/dL rise or peak >180
            if spike_magnitude > 50 or post_peak > 180:
                spikes.append({
                    "timestamp": carb.timestamp,
                    "carbs": carb.grams,
                    "pre_glucose": pre_glucose,
                    "peak_glucose": post_peak,
                    "spike_magnitude": spike_magnitude,
                })

        if meals_analyzed == 0:
            return {
                "meals_analyzed": 0,
                "spikes_detected": 0,
                "spike_rate": 0.0,
                "average_spike": 0.0,
                "evidence": ["No meals with sufficient glucose data found"]
            }

        spike_rate = len(spikes) / meals_analyzed * 100
        avg_spike = np.mean([s["spike_magnitude"] for s in spikes]) if spikes else 0

        evidence.append(f"Analyzed {meals_analyzed} meals with carbohydrate data")
        evidence.append(f"Post-meal spikes (>50 mg/dL rise or peak >180) detected: {len(spikes)}")

        if spikes:
            evidence.append(f"Average spike magnitude: {avg_spike:.0f} mg/dL")

            # Find meals with largest spikes
            top_spikes = sorted(spikes, key=lambda s: s["spike_magnitude"], reverse=True)[:3]
            for s in top_spikes:
                evidence.append(
                    f"  - {s['carbs']:.0f}g carbs: {s['pre_glucose']:.0f} → "
                    f"{s['peak_glucose']:.0f} mg/dL (+{s['spike_magnitude']:.0f})"
                )

        return {
            "meals_analyzed": meals_analyzed,
            "spikes_detected": len(spikes),
            "spike_rate": round(spike_rate, 1),
            "average_spike": round(avg_spike, 1),
            "evidence": evidence,
        }

    def analyze_insulin_sensitivity(
        self,
        readings: list[CGMReading],
        insulin: list[InsulinRecord],
        carbs: list[CarbRecord]
    ) -> dict:
        """
        Compute insulin sensitivity trends from the data.

        Note: This provides observational patterns only.
        Never calculates or suggests specific insulin doses.

        Args:
            readings: List of CGM readings
            insulin: List of insulin records
            carbs: List of carb records

        Returns:
            Dictionary with insulin sensitivity observations
        """
        if not readings or not insulin:
            return {
                "observations": ["Insufficient data for sensitivity analysis"],
                "patterns": [],
                "time_of_day_variation": {}
            }

        # Analyze bolus insulin events
        bolus_records = [i for i in insulin if i.insulin_type == "bolus"]

        if len(bolus_records) < 5:
            return {
                "observations": ["Insufficient bolus data for sensitivity analysis"],
                "patterns": [],
                "time_of_day_variation": {}
            }

        # Group by time of day
        morning_drops = []  # 6am-12pm
        afternoon_drops = []  # 12pm-6pm
        evening_drops = []  # 6pm-12am
        night_drops = []  # 12am-6am

        readings_df = pd.DataFrame([
            {"timestamp": r.timestamp, "glucose": r.glucose_mg_dl}
            for r in readings
        ]).sort_values("timestamp")

        observations = []

        for bolus in bolus_records:
            # Get glucose before and 2-4 hours after bolus
            pre_window = bolus.timestamp - timedelta(minutes=15)
            post_start = bolus.timestamp + timedelta(hours=2)
            post_end = bolus.timestamp + timedelta(hours=4)

            pre_mask = (readings_df["timestamp"] >= pre_window) & \
                       (readings_df["timestamp"] <= bolus.timestamp)
            post_mask = (readings_df["timestamp"] >= post_start) & \
                        (readings_df["timestamp"] <= post_end)

            pre_readings = readings_df[pre_mask]
            post_readings = readings_df[post_mask]

            if pre_readings.empty or post_readings.empty:
                continue

            pre_glucose = pre_readings["glucose"].mean()
            post_glucose = post_readings["glucose"].mean()
            drop = pre_glucose - post_glucose

            hour = bolus.timestamp.hour
            if 6 <= hour < 12:
                morning_drops.append(drop)
            elif 12 <= hour < 18:
                afternoon_drops.append(drop)
            elif 18 <= hour < 24:
                evening_drops.append(drop)
            else:
                night_drops.append(drop)

        time_of_day = {}

        if morning_drops:
            time_of_day["morning"] = {
                "average_response": round(np.mean(morning_drops), 1),
                "events": len(morning_drops)
            }
        if afternoon_drops:
            time_of_day["afternoon"] = {
                "average_response": round(np.mean(afternoon_drops), 1),
                "events": len(afternoon_drops)
            }
        if evening_drops:
            time_of_day["evening"] = {
                "average_response": round(np.mean(evening_drops), 1),
                "events": len(evening_drops)
            }
        if night_drops:
            time_of_day["night"] = {
                "average_response": round(np.mean(night_drops), 1),
                "events": len(night_drops)
            }

        # Generate observations (never specific doses)
        if time_of_day:
            responses = [(k, v["average_response"]) for k, v in time_of_day.items()]
            if len(responses) >= 2:
                max_response = max(responses, key=lambda x: x[1])
                min_response = min(responses, key=lambda x: x[1])

                if max_response[1] - min_response[1] > 20:
                    observations.append(
                        f"Glucose response to insulin appears stronger in the {max_response[0]} "
                        f"compared to {min_response[0]}"
                    )

        observations.append(
            "These patterns are observational only. Work with your healthcare team "
            "to interpret these findings and adjust your insulin regimen."
        )

        return {
            "observations": observations,
            "patterns": [],
            "time_of_day_variation": time_of_day,
        }

    def correlate_exercise_impact(
        self,
        readings: list[CGMReading],
        exercise: list[ExerciseRecord]
    ) -> dict:
        """
        Analyze the correlation between exercise and blood glucose.

        Args:
            readings: List of CGM readings
            exercise: List of exercise records

        Returns:
            Dictionary with exercise impact analysis
        """
        if not readings or not exercise:
            return {
                "sessions_analyzed": 0,
                "observations": ["Insufficient data for exercise analysis"],
                "average_glucose_change": 0.0,
            }

        readings_df = pd.DataFrame([
            {"timestamp": r.timestamp, "glucose": r.glucose_mg_dl}
            for r in readings
        ]).sort_values("timestamp")

        glucose_changes = []
        sessions_analyzed = 0
        observations = []

        for session in exercise:
            # Get glucose before exercise
            pre_start = session.timestamp - timedelta(minutes=30)
            pre_end = session.timestamp

            # Get glucose after exercise (1-3 hours)
            post_start = session.timestamp + timedelta(minutes=session.duration_minutes)
            post_end = post_start + timedelta(hours=3)

            pre_mask = (readings_df["timestamp"] >= pre_start) & \
                       (readings_df["timestamp"] <= pre_end)
            post_mask = (readings_df["timestamp"] >= post_start) & \
                        (readings_df["timestamp"] <= post_end)

            pre_readings = readings_df[pre_mask]
            post_readings = readings_df[post_mask]

            if pre_readings.empty or post_readings.empty:
                continue

            sessions_analyzed += 1
            pre_glucose = pre_readings["glucose"].mean()
            post_glucose = post_readings["glucose"].mean()
            change = post_glucose - pre_glucose
            glucose_changes.append({
                "change": change,
                "duration": session.duration_minutes,
                "intensity": session.intensity,
                "pre_glucose": pre_glucose,
            })

        if not glucose_changes:
            return {
                "sessions_analyzed": 0,
                "observations": ["No exercise sessions with matching glucose data found"],
                "average_glucose_change": 0.0,
            }

        avg_change = np.mean([c["change"] for c in glucose_changes])

        # Count sessions that led to drops vs rises
        drops = sum(1 for c in glucose_changes if c["change"] < -20)
        rises = sum(1 for c in glucose_changes if c["change"] > 20)

        observations.append(f"Analyzed {sessions_analyzed} exercise sessions")
        observations.append(f"Average glucose change after exercise: {avg_change:+.0f} mg/dL")

        if drops > rises:
            observations.append(
                f"Exercise tends to lower glucose ({drops} sessions with significant drops)"
            )
        elif rises > drops:
            observations.append(
                f"Exercise sometimes raises glucose ({rises} sessions with rises) - "
                "this may indicate adrenaline response or need for timing adjustments"
            )

        # Check for hypoglycemia risk
        hypo_events = sum(1 for c in glucose_changes if c["pre_glucose"] + c["change"] < 70)
        if hypo_events > 0:
            observations.append(
                f"Post-exercise glucose dropped below 70 mg/dL in {hypo_events} sessions - "
                "consider discussing timing and carb strategies with your healthcare team"
            )

        return {
            "sessions_analyzed": sessions_analyzed,
            "observations": observations,
            "average_glucose_change": round(avg_change, 1),
            "sessions_with_drops": drops,
            "sessions_with_rises": rises,
        }


class AnalysisCache:
    """
    Caching system for processed analysis results.

    Uses file hashing to avoid reprocessing the same exports.
    """

    def __init__(self, cache_dir: Path = CACHE_DIR):
        """Initialize the cache."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _compute_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        hasher = hashlib.sha256()

        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)

        return hasher.hexdigest()

    def _get_cache_path(self, file_hash: str) -> Path:
        """Get the cache file path for a given hash."""
        return self.cache_dir / f"{file_hash}.json"

    def get(self, file_path: Path) -> Optional[dict]:
        """
        Retrieve cached results for a file if available.

        Args:
            file_path: Path to the original export file

        Returns:
            Cached results dict or None if not cached
        """
        try:
            file_hash = self._compute_hash(file_path)
            cache_path = self._get_cache_path(file_hash)

            if cache_path.exists():
                with open(cache_path, 'r') as f:
                    cached = json.load(f)

                # Verify cache is still valid
                if cached.get("source_hash") == file_hash:
                    logger.info(f"Cache hit for {file_path.name}")
                    return cached.get("results")

            return None
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
            return None

    def set(self, file_path: Path, results: dict) -> None:
        """
        Store analysis results in cache.

        Args:
            file_path: Path to the original export file
            results: Analysis results to cache
        """
        try:
            file_hash = self._compute_hash(file_path)
            cache_path = self._get_cache_path(file_hash)

            cache_data = {
                "source_hash": file_hash,
                "source_file": str(file_path),
                "cached_at": datetime.now().isoformat(),
                "results": results,
            }

            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2, default=str)

            logger.info(f"Cached results for {file_path.name}")
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    def clear(self) -> int:
        """Clear all cached results. Returns number of files removed."""
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except Exception:
                pass
        return count


class GlookoAnalyzer:
    """
    Main API for Glooko data analysis.

    Integrates parsing, analysis, caching, and safety auditing
    into a single unified interface.

    Usage:
        analyzer = GlookoAnalyzer()
        results = analyzer.process_export("data/glooko/export.zip")
    """

    def __init__(self, use_cache: bool = True):
        """
        Initialize the analyzer.

        Args:
            use_cache: Whether to use caching for processed results
        """
        self.parser = GlookoParser()
        self.analyzer = DataAnalyzer()
        self.cache = AnalysisCache() if use_cache else None
        self.safety = SafetyAuditor()

    def process_export(self, file_path: str | Path) -> dict:
        """
        Process a Glooko export and return comprehensive analysis.

        Args:
            file_path: Path to ZIP file, directory, or CSV

        Returns:
            Dictionary containing:
            - time_in_range: TIR statistics
            - patterns: Detected patterns (dawn phenomenon, post-meal spikes)
            - recommendations: Contextual recommendations
            - analysis_period: Start and end dates
            - anomalies: Data quality issues
            - disclaimer: Safety disclaimer
            - safety_audit: Audit result from SafetyAuditor
        """
        path = Path(file_path)

        # Check cache first
        if self.cache and path.exists():
            cached = self.cache.get(path)
            if cached:
                return cached

        # Parse the export
        logger.info(f"Parsing export: {path}")
        parsed = self.parser.load_export(path)

        # Run all analyses
        logger.info("Calculating time in range...")
        tir = self.analyzer.calculate_time_in_range(parsed.cgm_readings)

        logger.info("Detecting dawn phenomenon...")
        dawn = self.analyzer.detect_dawn_phenomenon(parsed.cgm_readings)

        logger.info("Analyzing post-meal spikes...")
        post_meal = self.analyzer.detect_post_meal_spikes(
            parsed.cgm_readings,
            parsed.carb_records
        )

        logger.info("Analyzing insulin sensitivity...")
        sensitivity = self.analyzer.analyze_insulin_sensitivity(
            parsed.cgm_readings,
            parsed.insulin_records,
            parsed.carb_records
        )

        logger.info("Correlating exercise impact...")
        exercise = self.analyzer.correlate_exercise_impact(
            parsed.cgm_readings,
            parsed.exercise_records
        )

        # Generate recommendations (never specific doses)
        recommendations = self._generate_recommendations(
            tir, dawn, post_meal, sensitivity, exercise
        )

        # Compile results
        results = {
            "time_in_range": tir,
            "patterns": {
                "dawn_phenomenon": dawn,
                "post_meal_spikes": post_meal,
                "insulin_sensitivity": sensitivity,
                "exercise_impact": exercise,
            },
            "recommendations": recommendations,
            "analysis_period": {
                "start": parsed.start_date.isoformat() if parsed.start_date else None,
                "end": parsed.end_date.isoformat() if parsed.end_date else None,
                "days": (parsed.end_date - parsed.start_date).days + 1
                        if parsed.start_date and parsed.end_date else 0,
            },
            "data_summary": parsed.to_dict(),
            "anomalies": [
                {
                    "type": a.anomaly_type,
                    "description": a.description,
                    "severity": a.severity,
                }
                for a in parsed.anomalies
            ],
            "disclaimer": ANALYSIS_DISCLAIMER,
        }

        # Run safety audit on recommendations
        recommendations_text = "\n".join(recommendations)
        audit = self.safety.audit_text(recommendations_text, query="data_analysis")
        results["safety_audit"] = {
            "severity": audit.max_severity.value,
            "was_modified": audit.was_modified,
            "findings_count": len(audit.findings),
        }

        # Cache results
        if self.cache:
            self.cache.set(path, results)

        return results

    def _generate_recommendations(
        self,
        tir: dict,
        dawn: dict,
        post_meal: dict,
        sensitivity: dict,
        exercise: dict
    ) -> list[str]:
        """
        Generate contextual recommendations based on analysis.

        Note: Never suggests specific insulin doses.
        """
        recommendations = []

        # Time in range recommendations
        if tir["time_in_range_70_180"] < 70:
            recommendations.append(
                "Time in range is below the 70% target. Review patterns with your "
                "healthcare team to identify opportunities for improvement."
            )
        elif tir["time_in_range_70_180"] >= 70:
            recommendations.append(
                f"Time in range of {tir['time_in_range_70_180']}% meets the general target. "
                "Continue current management strategies."
            )

        if tir["time_below_70"] > 4:
            recommendations.append(
                f"Hypoglycemia rate ({tir['time_below_70']}%) exceeds the 4% target. "
                "Discuss strategies to reduce low glucose events with your healthcare team."
            )

        if tir["coefficient_of_variation"] > 36:
            recommendations.append(
                f"Glucose variability (CV: {tir['coefficient_of_variation']}%) is elevated. "
                "High variability may indicate timing or carb counting opportunities."
            )

        # Dawn phenomenon recommendations
        if dawn.get("detected"):
            recommendations.append(
                "Dawn phenomenon pattern detected. Consider discussing overnight "
                "basal adjustments or timing strategies with your healthcare team. "
                "See 'Think Like a Pancreas' Chapter 7 for detailed strategies."
            )

        # Post-meal recommendations
        if post_meal.get("spike_rate", 0) > 50:
            recommendations.append(
                f"Post-meal spikes occurring in {post_meal['spike_rate']:.0f}% of meals. "
                "Consider discussing pre-bolus timing, carb counting accuracy, or "
                "meal composition with your healthcare team."
            )

        # Exercise recommendations
        if exercise.get("sessions_analyzed", 0) > 0:
            if exercise.get("sessions_with_drops", 0) > exercise.get("sessions_with_rises", 0):
                recommendations.append(
                    "Exercise tends to lower your glucose. Review the CamAPS FX manual "
                    "for Ease-off mode timing recommendations before physical activity."
                )

        # Always add the disclaimer reminder
        recommendations.append(ANALYSIS_DISCLAIMER)

        return recommendations

    def format_report(self, results: dict) -> str:
        """
        Format analysis results as a readable text report.

        Args:
            results: Results dictionary from process_export()

        Returns:
            Formatted text report
        """
        lines = []
        lines.append("=" * 60)
        lines.append("DIABETES DATA ANALYSIS REPORT")
        lines.append("=" * 60)

        # Analysis period
        period = results.get("analysis_period", {})
        if period.get("start"):
            lines.append(f"\nAnalysis Period: {period['start'][:10]} to {period['end'][:10]}")
            lines.append(f"Days Analyzed: {period['days']}")

        # Time in range
        tir = results.get("time_in_range", {})
        lines.append("\n" + "-" * 40)
        lines.append("TIME IN RANGE")
        lines.append("-" * 40)
        lines.append(f"  In Range (70-180): {tir.get('time_in_range_70_180', 0)}%")
        lines.append(f"  Below 70:          {tir.get('time_below_70', 0)}%")
        lines.append(f"  Above 180:         {tir.get('time_above_180', 0)}%")
        lines.append(f"  Above 250:         {tir.get('time_above_250', 0)}%")
        lines.append(f"\n  Average Glucose:   {tir.get('average_glucose', 0)} mg/dL")
        lines.append(f"  Glucose SD:        {tir.get('glucose_std', 0)} mg/dL")
        lines.append(f"  CV:                {tir.get('coefficient_of_variation', 0)}%")
        lines.append(f"  Estimated A1C:     {tir.get('estimated_a1c', 0)}%")

        # Patterns
        patterns = results.get("patterns", {})

        lines.append("\n" + "-" * 40)
        lines.append("DETECTED PATTERNS")
        lines.append("-" * 40)

        # Dawn phenomenon
        dawn = patterns.get("dawn_phenomenon", {})
        status = "DETECTED" if dawn.get("detected") else "Not detected"
        lines.append(f"\nDawn Phenomenon: {status}")
        for evidence in dawn.get("evidence", []):
            lines.append(f"  - {evidence}")

        # Post-meal spikes
        post_meal = patterns.get("post_meal_spikes", {})
        lines.append(f"\nPost-Meal Spikes:")
        lines.append(f"  Meals analyzed: {post_meal.get('meals_analyzed', 0)}")
        lines.append(f"  Spikes detected: {post_meal.get('spikes_detected', 0)}")
        lines.append(f"  Spike rate: {post_meal.get('spike_rate', 0)}%")

        # Exercise impact
        exercise = patterns.get("exercise_impact", {})
        if exercise.get("sessions_analyzed", 0) > 0:
            lines.append(f"\nExercise Impact:")
            for obs in exercise.get("observations", []):
                lines.append(f"  - {obs}")

        # Recommendations
        lines.append("\n" + "-" * 40)
        lines.append("RECOMMENDATIONS")
        lines.append("-" * 40)
        for rec in results.get("recommendations", []):
            lines.append(f"\n• {rec}")

        # Anomalies
        anomalies = results.get("anomalies", [])
        if anomalies:
            lines.append("\n" + "-" * 40)
            lines.append("DATA QUALITY NOTES")
            lines.append("-" * 40)
            for anomaly in anomalies[:5]:  # Limit to first 5
                lines.append(f"  [{anomaly['severity'].upper()}] {anomaly['description']}")

        # Disclaimer
        lines.append("\n" + "=" * 60)
        lines.append(f"⚠️  {results.get('disclaimer', ANALYSIS_DISCLAIMER)}")
        lines.append("=" * 60)

        return "\n".join(lines)


def generate_research_queries(results: dict, max_queries: int = 5) -> list[dict]:
    """
    Generate contextual research questions based on analysis results.

    Creates questions formatted for the Triage Agent to route to appropriate
    knowledge sources (Think Like a Pancreas, CamAPS FX manual, Ypsomed manual).

    Args:
        results: Analysis results from GlookoAnalyzer.process_export()
        max_queries: Maximum number of queries to generate (default: 5)

    Returns:
        List of dictionaries containing:
        - question: The research question text
        - pattern_type: Type of pattern that triggered this question
        - confidence: Confidence score (0-100) of the pattern
        - priority: Priority ranking (1=highest)
        - knowledge_source: Suggested knowledge source to query
    """
    queries = []

    patterns = results.get("patterns", {})
    tir = results.get("time_in_range", {})

    # --- Dawn Phenomenon Queries ---
    dawn = patterns.get("dawn_phenomenon", {})
    if dawn.get("detected"):
        confidence = dawn.get("confidence", 0)

        queries.append({
            "question": "What strategies does Think Like a Pancreas recommend for managing dawn phenomenon?",
            "pattern_type": "dawn_phenomenon",
            "confidence": confidence,
            "priority": 1 if confidence >= 60 else 2,
            "knowledge_source": "think_like_pancreas",
            "context": f"Dawn phenomenon detected on {dawn.get('days_analyzed', 0)} days "
                      f"with {dawn.get('average_rise_rate', 0):.1f} mg/dL/hour average rise"
        })

        queries.append({
            "question": "How should I adjust CamAPS FX Boost mode timing to address early morning glucose rises?",
            "pattern_type": "dawn_phenomenon",
            "confidence": confidence,
            "priority": 2,
            "knowledge_source": "camaps_guide",
            "context": "Early morning highs between 3am-8am"
        })

        if confidence >= 50:
            queries.append({
                "question": "What overnight basal rate adjustment strategies can help with dawn phenomenon?",
                "pattern_type": "dawn_phenomenon",
                "confidence": confidence,
                "priority": 3,
                "knowledge_source": "think_like_pancreas",
                "context": "Consistent morning glucose elevation pattern"
            })

    # --- Post-Meal Spike Queries ---
    post_meal = patterns.get("post_meal_spikes", {})
    spike_rate = post_meal.get("spike_rate", 0)

    if spike_rate > 50:
        avg_spike = post_meal.get("average_spike", 0)
        meals_analyzed = post_meal.get("meals_analyzed", 0)

        queries.append({
            "question": "What does Think Like a Pancreas say about optimal meal bolus timing to prevent post-meal spikes?",
            "pattern_type": "post_meal_spikes",
            "confidence": spike_rate,
            "priority": 1 if spike_rate >= 70 else 2,
            "knowledge_source": "think_like_pancreas",
            "context": f"Post-meal spikes in {spike_rate:.0f}% of {meals_analyzed} meals, "
                      f"average spike: {avg_spike:.0f} mg/dL"
        })

        queries.append({
            "question": "How can I use the Ypsomed pump's extended bolus feature to reduce post-meal glucose spikes?",
            "pattern_type": "post_meal_spikes",
            "confidence": spike_rate,
            "priority": 2,
            "knowledge_source": "ypsomed_manual",
            "context": f"High-carb meals causing {avg_spike:.0f} mg/dL average spike"
        })

        if spike_rate >= 70:
            queries.append({
                "question": "What pre-bolus timing does CamAPS FX recommend for optimal post-meal control?",
                "pattern_type": "post_meal_spikes",
                "confidence": spike_rate,
                "priority": 2,
                "knowledge_source": "camaps_guide",
                "context": "Significant post-meal excursions"
            })

    # --- Time in Range Queries ---
    time_in_range = tir.get("time_in_range_70_180", 0)
    time_below = tir.get("time_below_70", 0)
    time_above = tir.get("time_above_180", 0)

    if time_in_range < 70:
        # Below target TIR
        queries.append({
            "question": "What are the key strategies in Think Like a Pancreas for improving time in range?",
            "pattern_type": "time_in_range",
            "confidence": 100 - time_in_range,  # Higher confidence for worse TIR
            "priority": 1,
            "knowledge_source": "think_like_pancreas",
            "context": f"Current TIR: {time_in_range:.1f}% (target: 70%)"
        })

    if time_below > 4:
        # Excessive hypoglycemia
        queries.append({
            "question": "How can CamAPS FX Ease-off mode help reduce hypoglycemia frequency?",
            "pattern_type": "hypoglycemia",
            "confidence": min(time_below * 10, 100),
            "priority": 1,  # Hypos are always high priority
            "knowledge_source": "camaps_guide",
            "context": f"Time below 70: {time_below:.1f}% (target: <4%)"
        })

        queries.append({
            "question": "What does Think Like a Pancreas recommend for preventing low blood sugar episodes?",
            "pattern_type": "hypoglycemia",
            "confidence": min(time_below * 10, 100),
            "priority": 1,
            "knowledge_source": "think_like_pancreas",
            "context": "Elevated hypoglycemia risk"
        })

    # --- Insulin Sensitivity Queries ---
    sensitivity = patterns.get("insulin_sensitivity", {})
    time_variation = sensitivity.get("time_of_day_variation", {})

    if len(time_variation) >= 2:
        # Find periods with most/least sensitivity
        periods = [(k, v["average_response"]) for k, v in time_variation.items()]
        if periods:
            max_period = max(periods, key=lambda x: abs(x[1]))
            min_period = min(periods, key=lambda x: abs(x[1]))

            if abs(max_period[1] - min_period[1]) > 15:
                queries.append({
                    "question": "How does Think Like a Pancreas explain time-of-day insulin sensitivity variations?",
                    "pattern_type": "insulin_sensitivity",
                    "confidence": 70,
                    "priority": 3,
                    "knowledge_source": "think_like_pancreas",
                    "context": f"Insulin response varies: {max_period[0]} ({max_period[1]:+.0f} mg/dL) "
                              f"vs {min_period[0]} ({min_period[1]:+.0f} mg/dL)"
                })

    # --- Exercise Impact Queries ---
    exercise = patterns.get("exercise_impact", {})
    sessions = exercise.get("sessions_analyzed", 0)

    if sessions > 0:
        avg_change = exercise.get("average_glucose_change", 0)
        drops = exercise.get("sessions_with_drops", 0)

        if drops > 0:
            queries.append({
                "question": "When should I activate CamAPS FX Ease-off mode before exercise to prevent lows?",
                "pattern_type": "exercise_impact",
                "confidence": (drops / sessions) * 100 if sessions > 0 else 0,
                "priority": 2,
                "knowledge_source": "camaps_guide",
                "context": f"Exercise lowered glucose in {drops} of {sessions} sessions"
            })

        queries.append({
            "question": "What exercise management strategies does Think Like a Pancreas recommend for pump users?",
            "pattern_type": "exercise_impact",
            "confidence": 60,
            "priority": 3,
            "knowledge_source": "think_like_pancreas",
            "context": f"Average glucose change with exercise: {avg_change:+.0f} mg/dL"
        })

    # --- Glucose Variability Queries ---
    cv = tir.get("coefficient_of_variation", 0)
    if cv > 36:
        queries.append({
            "question": "What strategies does Think Like a Pancreas suggest for reducing glucose variability?",
            "pattern_type": "glucose_variability",
            "confidence": min((cv - 36) * 5, 100),
            "priority": 2,
            "knowledge_source": "think_like_pancreas",
            "context": f"Coefficient of variation: {cv:.1f}% (target: <36%)"
        })

    # Sort by priority, then by confidence
    queries.sort(key=lambda q: (q["priority"], -q["confidence"]))

    # Limit to max_queries and assign final priority rankings
    queries = queries[:max_queries]
    for i, query in enumerate(queries):
        query["priority"] = i + 1

    return queries


def format_research_queries(queries: list[dict]) -> str:
    """
    Format research queries as readable text for display.

    Args:
        queries: List of query dictionaries from generate_research_queries()

    Returns:
        Formatted text string
    """
    if not queries:
        return "No research queries generated based on the analysis."

    lines = []
    lines.append("=" * 60)
    lines.append(" SUGGESTED RESEARCH QUERIES")
    lines.append(" (Route through Triage Agent for knowledge source lookup)")
    lines.append("=" * 60)

    for query in queries:
        lines.append(f"\n  [{query['priority']}] {query['question']}")
        lines.append(f"      Pattern: {query['pattern_type'].replace('_', ' ').title()}")
        lines.append(f"      Confidence: {query['confidence']:.0f}%")
        lines.append(f"      Source: {query['knowledge_source'].replace('_', ' ').title()}")
        if query.get("context"):
            lines.append(f"      Context: {query['context']}")

    lines.append("\n" + "-" * 60)
    lines.append("  To execute: Pass these queries to the Triage Agent")
    lines.append("  Example: triage.process(queries[0]['question'])")
    lines.append("-" * 60)

    return "\n".join(lines)


# CLI interface
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Analyze Glooko diabetes data exports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python -m agents.data_ingestion data/glooko/export.zip
  python -m agents.data_ingestion data/glooko/ --no-cache
  python -m agents.data_ingestion data/glooko/cgm.csv --json

{ANALYSIS_DISCLAIMER}
"""
    )

    parser.add_argument(
        "file_path",
        help="Path to Glooko export (ZIP, directory, or CSV)"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching of results"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of formatted report"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the analysis cache and exit"
    )

    args = parser.parse_args()

    # Handle cache clearing
    if args.clear_cache:
        cache = AnalysisCache()
        count = cache.clear()
        print(f"Cleared {count} cached analysis files")
        sys.exit(0)

    # Process the export
    try:
        analyzer = GlookoAnalyzer(use_cache=not args.no_cache)
        results = analyzer.process_export(args.file_path)

        if args.json:
            print(json.dumps(results, indent=2, default=str))
        else:
            print(analyzer.format_report(results))

        sys.exit(0)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
