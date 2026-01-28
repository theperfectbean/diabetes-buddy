#!/usr/bin/env python3
"""
Test script for GlookoAnalyzer

Processes real Glooko export files from data/glooko/ and displays
analysis results in a readable format.

Usage:
    python scripts/test_analyzer.py
    python scripts/test_analyzer.py --verbose
    python scripts/test_analyzer.py --file data/glooko/specific_file.zip
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents import GlookoAnalyzer
from agents.data_ingestion import (
    GlookoParser,
    ANALYSIS_DISCLAIMER,
    generate_research_queries,
    format_research_queries,
)


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging for the test script."""
    level = logging.DEBUG if verbose else logging.INFO

    # Create custom formatter that highlights warnings/errors
    class ColorFormatter(logging.Formatter):
        COLORS = {
            logging.DEBUG: "\033[36m",    # Cyan
            logging.INFO: "\033[32m",     # Green
            logging.WARNING: "\033[33m",  # Yellow
            logging.ERROR: "\033[31m",    # Red
        }
        RESET = "\033[0m"

        def format(self, record):
            color = self.COLORS.get(record.levelno, "")
            record.levelname = f"{color}{record.levelname}{self.RESET}"
            return super().format(record)

    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S"
    ))

    logger = logging.getLogger("test_analyzer")
    logger.setLevel(level)
    logger.addHandler(handler)

    # Also configure the data_ingestion logger
    ingestion_logger = logging.getLogger("agents.data_ingestion")
    ingestion_logger.setLevel(level)
    ingestion_logger.addHandler(handler)

    return logger


def find_glooko_files(data_dir: Path) -> list[Path]:
    """Find all processable files in the glooko data directory."""
    files = []

    if not data_dir.exists():
        return files

    # Look for ZIP files
    files.extend(data_dir.glob("*.zip"))

    # Look for CSV files
    files.extend(data_dir.glob("*.csv"))

    # Sort by modification time (newest first)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    return files


def inspect_csv_columns(file_path: Path, logger: logging.Logger) -> None:
    """Log the columns found in a CSV file for debugging."""
    import pandas as pd

    try:
        if file_path.suffix.lower() == ".csv":
            df = pd.read_csv(file_path, nrows=5)
            logger.debug(f"Columns in {file_path.name}: {list(df.columns)}")
            logger.debug(f"Sample data:\n{df.head(2).to_string()}")
        elif file_path.suffix.lower() == ".zip":
            import zipfile
            with zipfile.ZipFile(file_path, 'r') as zf:
                csv_files = [f for f in zf.namelist() if f.lower().endswith('.csv')]
                logger.debug(f"ZIP contains {len(csv_files)} CSV files: {csv_files}")
                for csv_name in csv_files[:3]:  # Inspect first 3
                    with zf.open(csv_name) as f:
                        content = f.read().decode('utf-8')
                        from io import StringIO
                        df = pd.read_csv(StringIO(content), nrows=5)
                        logger.debug(f"Columns in {csv_name}: {list(df.columns)}")
    except Exception as e:
        logger.warning(f"Could not inspect file structure: {e}")


def print_section(title: str, char: str = "=") -> None:
    """Print a formatted section header."""
    width = 60
    print(f"\n{char * width}")
    print(f" {title}")
    print(f"{char * width}")


def print_time_in_range(tir: dict) -> None:
    """Print time-in-range statistics in a readable format."""
    print_section("TIME IN RANGE STATISTICS", "-")

    if tir.get("total_readings", 0) == 0:
        print("  No CGM readings found in the data.")
        return

    print(f"\n  Total Readings: {tir.get('total_readings', 0):,}")
    print()

    # Visual bar for TIR
    in_range = tir.get("time_in_range_70_180", 0)
    below = tir.get("time_below_70", 0)
    above_180 = tir.get("time_above_180", 0)
    above_250 = tir.get("time_above_250", 0)

    bar_width = 40
    in_range_bars = int(in_range / 100 * bar_width)
    below_bars = int(below / 100 * bar_width)
    above_bars = int((above_180) / 100 * bar_width)

    print("  Distribution:")
    print(f"    Below 70:      {'#' * below_bars:<{bar_width}} {below:5.1f}%")
    print(f"    In Range:      {'#' * in_range_bars:<{bar_width}} {in_range:5.1f}%")
    print(f"    Above 180:     {'#' * above_bars:<{bar_width}} {above_180:5.1f}%")
    print(f"    Above 250:     {' ' * bar_width} {above_250:5.1f}%")
    print()

    # Key metrics
    print("  Key Metrics:")
    print(f"    Average Glucose:    {tir.get('average_glucose', 0):6.1f} mg/dL")
    print(f"    Standard Deviation: {tir.get('glucose_std', 0):6.1f} mg/dL")
    print(f"    CV (Variability):   {tir.get('coefficient_of_variation', 0):6.1f}%")
    print(f"    Estimated A1C:      {tir.get('estimated_a1c', 0):6.1f}%")

    # Targets assessment
    print("\n  Target Assessment:")
    if in_range >= 70:
        print("    [OK] Time in range meets 70% target")
    else:
        print(f"    [!!] Time in range ({in_range:.1f}%) below 70% target")

    if below <= 4:
        print("    [OK] Hypoglycemia within 4% target")
    else:
        print(f"    [!!] Hypoglycemia ({below:.1f}%) exceeds 4% target")

    cv = tir.get("coefficient_of_variation", 0)
    if cv <= 36:
        print("    [OK] Glucose variability within healthy range")
    else:
        print(f"    [!!] Glucose variability ({cv:.1f}%) elevated (target <36%)")


def print_patterns(patterns: dict) -> None:
    """Print detected patterns in a readable format."""
    print_section("DETECTED PATTERNS", "-")

    # Dawn Phenomenon
    dawn = patterns.get("dawn_phenomenon", {})
    print("\n  Dawn Phenomenon (3am-8am):")
    if dawn.get("detected"):
        print(f"    Status: DETECTED (confidence: {dawn.get('confidence', 0):.0f}%)")
    else:
        print("    Status: Not detected")

    for evidence in dawn.get("evidence", []):
        print(f"      - {evidence}")

    if dawn.get("days_analyzed", 0) > 0:
        print(f"    Days analyzed: {dawn['days_analyzed']}")

    # Post-Meal Spikes
    post_meal = patterns.get("post_meal_spikes", {})
    print("\n  Post-Meal Spikes:")
    meals = post_meal.get("meals_analyzed", 0)
    spikes = post_meal.get("spikes_detected", 0)

    if meals > 0:
        print(f"    Meals analyzed: {meals}")
        print(f"    Spikes detected: {spikes} ({post_meal.get('spike_rate', 0):.1f}%)")
        if post_meal.get("average_spike", 0) > 0:
            print(f"    Average spike: {post_meal['average_spike']:.0f} mg/dL")
    else:
        print("    Insufficient meal data for analysis")

    for evidence in post_meal.get("evidence", [])[:3]:
        if not evidence.startswith("Analyzed"):
            print(f"      - {evidence}")

    # Insulin Sensitivity
    sensitivity = patterns.get("insulin_sensitivity", {})
    print("\n  Insulin Sensitivity Patterns:")

    time_variation = sensitivity.get("time_of_day_variation", {})
    if time_variation:
        for period, data in time_variation.items():
            print(f"    {period.capitalize():10}: avg response {data['average_response']:+.0f} mg/dL "
                  f"({data['events']} events)")

    for obs in sensitivity.get("observations", []):
        if "Work with your healthcare" not in obs:
            print(f"      - {obs}")

    # Exercise Impact
    exercise = patterns.get("exercise_impact", {})
    print("\n  Exercise Impact:")

    sessions = exercise.get("sessions_analyzed", 0)
    if sessions > 0:
        print(f"    Sessions analyzed: {sessions}")
        print(f"    Average glucose change: {exercise.get('average_glucose_change', 0):+.0f} mg/dL")

        for obs in exercise.get("observations", [])[:3]:
            if not obs.startswith("Analyzed"):
                print(f"      - {obs}")
    else:
        print("    No exercise sessions with matching glucose data")


def print_recommendations(recommendations: list[str]) -> None:
    """Print recommendations in a readable format."""
    print_section("RECOMMENDATIONS", "-")

    for i, rec in enumerate(recommendations, 1):
        if rec == ANALYSIS_DISCLAIMER:
            continue  # Skip, we'll print it at the end

        # Wrap long recommendations
        words = rec.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            if current_length + len(word) + 1 > 55:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_length = len(word)
            else:
                current_line.append(word)
                current_length += len(word) + 1

        if current_line:
            lines.append(" ".join(current_line))

        print(f"\n  {i}. {lines[0]}")
        for line in lines[1:]:
            print(f"     {line}")


def print_anomalies(anomalies: list[dict], logger: logging.Logger) -> None:
    """Print and log data anomalies."""
    if not anomalies:
        return

    print_section("DATA QUALITY NOTES", "-")

    # Group by severity
    critical = [a for a in anomalies if a["severity"] == "critical"]
    warnings = [a for a in anomalies if a["severity"] == "warning"]
    info = [a for a in anomalies if a["severity"] == "info"]

    if critical:
        print("\n  Critical Issues:")
        for a in critical[:5]:
            print(f"    [CRITICAL] {a['description']}")
            logger.error(f"Data anomaly: {a['type']} - {a['description']}")

    if warnings:
        print("\n  Warnings:")
        for a in warnings[:5]:
            print(f"    [WARNING] {a['description']}")
            logger.warning(f"Data anomaly: {a['type']} - {a['description']}")

    if info:
        print(f"\n  Info: {len(info)} minor notes (use --verbose for details)")
        for a in info:
            logger.debug(f"Data note: {a['type']} - {a['description']}")

    if len(anomalies) > 15:
        print(f"\n  ... and {len(anomalies) - 15} more issues")


def main():
    """Main entry point for the test script."""
    parser = argparse.ArgumentParser(
        description="Test GlookoAnalyzer with real export files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--file", "-f",
        type=Path,
        help="Specific file to process (default: first file in data/glooko/)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging for debugging"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable result caching"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON results"
    )

    args = parser.parse_args()
    logger = setup_logging(args.verbose)

    # Determine which file to process
    data_dir = PROJECT_ROOT / "data" / "glooko"

    if args.file:
        if not args.file.exists():
            logger.error(f"File not found: {args.file}")
            sys.exit(1)
        target_file = args.file
    else:
        # Find files in data/glooko/
        files = find_glooko_files(data_dir)

        if not files:
            print_section("GLOOKO ANALYZER TEST")
            print("\n  No files found in data/glooko/")
            print("\n  To test the analyzer:")
            print("    1. Export your data from Glooko (Settings > Export Data)")
            print("    2. Save the ZIP file to data/glooko/")
            print("    3. Run this script again")
            print(f"\n  Data directory: {data_dir}")
            print("\n  Supported formats:")
            print("    - ZIP archives containing CSV files")
            print("    - Individual CSV files")
            print("    - Directories with CSV files")
            sys.exit(0)

        target_file = files[0]

        if len(files) > 1:
            logger.info(f"Found {len(files)} files, processing most recent: {target_file.name}")
            logger.debug(f"Other files: {[f.name for f in files[1:]]}")

    # Inspect file structure if verbose
    if args.verbose:
        inspect_csv_columns(target_file, logger)

    # Process the file
    print_section("GLOOKO ANALYZER TEST")
    print(f"\n  Processing: {target_file.name}")
    print(f"  File size: {target_file.stat().st_size / 1024:.1f} KB")

    try:
        analyzer = GlookoAnalyzer(use_cache=not args.no_cache)
        logger.info("Starting analysis...")

        results = analyzer.process_export(target_file)

        logger.info("Analysis complete")

        # Output results
        if args.json:
            import json
            print(json.dumps(results, indent=2, default=str))
        else:
            # Analysis period
            period = results.get("analysis_period", {})
            if period.get("start"):
                print(f"\n  Period: {period['start'][:10]} to {period['end'][:10]} "
                      f"({period['days']} days)")

            # Data summary
            summary = results.get("data_summary", {})
            print(f"\n  Data loaded:")
            print(f"    - CGM readings:     {summary.get('cgm_count', 0):,}")
            print(f"    - Insulin records:  {summary.get('insulin_count', 0):,}")
            print(f"    - Carb entries:     {summary.get('carb_count', 0):,}")
            print(f"    - Exercise logs:    {summary.get('exercise_count', 0):,}")

            # Main sections
            print_time_in_range(results.get("time_in_range", {}))
            print_patterns(results.get("patterns", {}))
            print_recommendations(results.get("recommendations", []))
            print_anomalies(results.get("anomalies", []), logger)

            # Safety audit status
            audit = results.get("safety_audit", {})
            if audit.get("was_modified"):
                print("\n  [SAFETY] Response was modified by SafetyAuditor")

            # Generate and display research queries
            queries = generate_research_queries(results)
            if queries:
                print("\n" + format_research_queries(queries))

            # Final disclaimer
            print("\n" + "=" * 60)
            print(f"  {ANALYSIS_DISCLAIMER}")
            print("=" * 60)

        sys.exit(0)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)

    except ValueError as e:
        logger.error(f"Invalid file format: {e}")
        print("\n  The file format doesn't match expected Glooko export structure.")
        print("  Check that you're using a Glooko data export (not a different app).")

        if args.verbose:
            print("\n  Debug: Inspecting file structure...")
            inspect_csv_columns(target_file, logger)
        else:
            print("  Run with --verbose for detailed column information.")

        sys.exit(1)

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"\n  Error processing file: {e}")
        print("  Run with --verbose for full traceback.")
        sys.exit(1)


if __name__ == "__main__":
    main()
