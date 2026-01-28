#!/usr/bin/env python3
"""
Diabetes Buddy - Complete Analysis and Advice Workflow

Processes Glooko data exports and generates personalized research queries
routed through the agent architecture for actionable insights.

This script demonstrates the full workflow:
1. Load and analyze Glooko export data
2. Detect patterns (dawn phenomenon, post-meal spikes, etc.)
3. Generate contextual research queries
4. Route queries through Triage Agent to knowledge sources
5. Present structured, patient-friendly report

Usage:
    python scripts/analyze_and_advise.py
    python scripts/analyze_and_advise.py --file data/glooko/export.zip
    python scripts/analyze_and_advise.py --limit 3 --output report.txt
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls):
        """Disable colors for file output."""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.RED = ""
        cls.BLUE = ""
        cls.CYAN = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RESET = ""


def colorize(text: str, color: str) -> str:
    """Apply color to text."""
    return f"{color}{text}{Colors.RESET}"


def status_color(value: float, good_threshold: float, warn_threshold: float,
                 higher_is_better: bool = True) -> str:
    """Get color based on value thresholds."""
    if higher_is_better:
        if value >= good_threshold:
            return Colors.GREEN
        elif value >= warn_threshold:
            return Colors.YELLOW
        else:
            return Colors.RED
    else:
        if value <= good_threshold:
            return Colors.GREEN
        elif value <= warn_threshold:
            return Colors.YELLOW
        else:
            return Colors.RED


def find_latest_export(data_dir: Path) -> Optional[Path]:
    """Find the most recent Glooko export file."""
    files = []

    if data_dir.exists():
        files.extend(data_dir.glob("*.zip"))
        files.extend(data_dir.glob("*.csv"))

    if not files:
        return None

    # Sort by modification time, newest first
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0]


def format_header(title: str, width: int = 70) -> str:
    """Format a section header."""
    return f"\n{Colors.BOLD}{'=' * width}\n {title}\n{'=' * width}{Colors.RESET}"


def format_subheader(title: str, width: int = 70) -> str:
    """Format a subsection header."""
    return f"\n{Colors.CYAN}{'-' * width}\n {title}\n{'-' * width}{Colors.RESET}"


def print_data_summary(results: dict, output) -> None:
    """Print the data summary section."""
    print(format_header("DATA SUMMARY"), file=output)

    period = results.get("analysis_period", {})
    summary = results.get("data_summary", {})
    tir = results.get("time_in_range", {})

    # Date range
    if period.get("start"):
        start = period["start"][:10]
        end = period["end"][:10]
        days = period.get("days", 0)
        print(f"\n  {Colors.BOLD}Analysis Period:{Colors.RESET} {start} to {end} ({days} days)", file=output)

    # Data counts
    print(f"\n  {Colors.BOLD}Data Loaded:{Colors.RESET}", file=output)
    print(f"    CGM Readings:    {summary.get('cgm_count', 0):>8,}", file=output)
    print(f"    Insulin Records: {summary.get('insulin_count', 0):>8,}", file=output)
    print(f"    Carb Entries:    {summary.get('carb_count', 0):>8,}", file=output)
    print(f"    Exercise Logs:   {summary.get('exercise_count', 0):>8,}", file=output)

    # Time in range with color coding
    time_in_range = tir.get("time_in_range_70_180", 0)
    time_below = tir.get("time_below_70", 0)
    time_above = tir.get("time_above_180", 0)

    tir_color = status_color(time_in_range, 70, 50, higher_is_better=True)
    hypo_color = status_color(time_below, 4, 8, higher_is_better=False)

    print(f"\n  {Colors.BOLD}Glucose Metrics:{Colors.RESET}", file=output)
    print(f"    Time in Range (70-180): {tir_color}{time_in_range:>5.1f}%{Colors.RESET} "
          f"{'[TARGET MET]' if time_in_range >= 70 else '[BELOW TARGET]'}", file=output)
    print(f"    Time Below 70:          {hypo_color}{time_below:>5.1f}%{Colors.RESET} "
          f"{'[OK]' if time_below <= 4 else '[ELEVATED]'}", file=output)
    print(f"    Time Above 180:         {time_above:>5.1f}%", file=output)

    # Additional metrics
    avg_glucose = tir.get("average_glucose", 0)
    cv = tir.get("coefficient_of_variation", 0)
    a1c = tir.get("estimated_a1c", 0)

    cv_color = status_color(cv, 36, 45, higher_is_better=False)

    print(f"\n    Average Glucose:        {avg_glucose:>5.1f} mg/dL", file=output)
    print(f"    Variability (CV):       {cv_color}{cv:>5.1f}%{Colors.RESET} "
          f"{'[STABLE]' if cv <= 36 else '[VARIABLE]'}", file=output)
    print(f"    Estimated A1C:          {a1c:>5.1f}%", file=output)


def print_detected_patterns(results: dict, output) -> None:
    """Print the detected patterns section."""
    print(format_header("DETECTED PATTERNS"), file=output)

    patterns = results.get("patterns", {})
    pattern_count = 0

    # Dawn Phenomenon
    dawn = patterns.get("dawn_phenomenon", {})
    if dawn.get("detected"):
        pattern_count += 1
        confidence = dawn.get("confidence", 0)
        conf_color = Colors.YELLOW if confidence < 70 else Colors.RED

        print(f"\n  {Colors.BOLD}1. Dawn Phenomenon{Colors.RESET} "
              f"[{conf_color}Confidence: {confidence:.0f}%{Colors.RESET}]", file=output)
        print(f"     Rising glucose detected between 3am-8am", file=output)

        rise_rate = dawn.get("average_rise_rate", 0)
        days = dawn.get("days_analyzed", 0)
        print(f"     Average rise: {rise_rate:.1f} mg/dL per hour", file=output)
        print(f"     Observed on {dawn.get('days_analyzed', 0)} days analyzed", file=output)

    # Post-Meal Spikes
    post_meal = patterns.get("post_meal_spikes", {})
    spike_rate = post_meal.get("spike_rate", 0)
    if spike_rate > 50:
        pattern_count += 1
        spike_color = Colors.YELLOW if spike_rate < 70 else Colors.RED

        print(f"\n  {Colors.BOLD}2. Post-Meal Spikes{Colors.RESET} "
              f"[{spike_color}Frequency: {spike_rate:.0f}%{Colors.RESET}]", file=output)

        avg_spike = post_meal.get("average_spike", 0)
        meals = post_meal.get("meals_analyzed", 0)
        print(f"     Spikes detected in {spike_rate:.0f}% of {meals} meals", file=output)
        print(f"     Average spike magnitude: {avg_spike:.0f} mg/dL", file=output)

    # Insulin Sensitivity Variation
    sensitivity = patterns.get("insulin_sensitivity", {})
    time_variation = sensitivity.get("time_of_day_variation", {})
    if len(time_variation) >= 2:
        pattern_count += 1

        print(f"\n  {Colors.BOLD}3. Insulin Sensitivity Patterns{Colors.RESET} "
              f"[{Colors.CYAN}Informational{Colors.RESET}]", file=output)

        for period, data in sorted(time_variation.items()):
            response = data.get("average_response", 0)
            events = data.get("events", 0)
            print(f"     {period.capitalize():12}: {response:+.0f} mg/dL response ({events} events)", file=output)

    # Exercise Impact
    exercise = patterns.get("exercise_impact", {})
    sessions = exercise.get("sessions_analyzed", 0)
    if sessions > 0:
        pattern_count += 1
        avg_change = exercise.get("average_glucose_change", 0)

        print(f"\n  {Colors.BOLD}4. Exercise Impact{Colors.RESET} "
              f"[{Colors.CYAN}Informational{Colors.RESET}]", file=output)
        print(f"     {sessions} exercise sessions analyzed", file=output)
        print(f"     Average glucose change: {avg_change:+.0f} mg/dL", file=output)

    if pattern_count == 0:
        print(f"\n  {Colors.GREEN}No significant patterns detected.{Colors.RESET}", file=output)
        print("  Your glucose control appears stable based on this data.", file=output)
    else:
        print(f"\n  {Colors.DIM}Total patterns detected: {pattern_count}{Colors.RESET}", file=output)


def print_research_queries(queries: list[dict], output) -> None:
    """Print the generated research queries section."""
    print(format_header("PERSONALIZED RESEARCH QUESTIONS"), file=output)

    if not queries:
        print(f"\n  {Colors.GREEN}No specific research queries generated.{Colors.RESET}", file=output)
        print("  Your current management appears on track.", file=output)
        return

    print(f"\n  Based on your data, here are prioritized questions to explore:\n", file=output)

    for query in queries:
        priority = query.get("priority", 0)
        question = query.get("question", "")
        pattern = query.get("pattern_type", "").replace("_", " ").title()
        confidence = query.get("confidence", 0)
        source = query.get("knowledge_source", "").replace("_", " ").title()
        context = query.get("context", "")

        # Color based on confidence
        if confidence >= 70:
            priority_color = Colors.RED
            priority_label = "HIGH"
        elif confidence >= 50:
            priority_color = Colors.YELLOW
            priority_label = "MEDIUM"
        else:
            priority_color = Colors.CYAN
            priority_label = "LOW"

        print(f"  {Colors.BOLD}[{priority}]{Colors.RESET} {priority_color}[{priority_label}]{Colors.RESET}", file=output)
        print(f"      {Colors.BOLD}{question}{Colors.RESET}", file=output)
        print(f"      {Colors.DIM}Pattern: {pattern} | Source: {source}{Colors.RESET}", file=output)
        if context:
            print(f"      {Colors.DIM}Context: {context}{Colors.RESET}", file=output)
        print(file=output)


def print_routing_plan(queries: list[dict], triage_available: bool, output) -> None:
    """Print the agent routing plan section."""
    print(format_header("KNOWLEDGE SOURCE ROUTING"), file=output)

    if not queries:
        print(f"\n  No queries to route.", file=output)
        return

    # Group queries by knowledge source
    sources = {}
    for query in queries:
        source = query.get("knowledge_source", "unknown")
        if source not in sources:
            sources[source] = []
        sources[source].append(query)

    source_descriptions = {
        "think_like_pancreas": "Think Like a Pancreas (Gary Scheiner) - Behavioral strategies",
        "camaps_guide": "CamAPS FX User Guide - Hybrid closed-loop system",
        "ypsomed_manual": "Ypsomed Pump Manual - Hardware procedures",
    }

    print(f"\n  Queries will be routed to these knowledge sources:\n", file=output)

    for source, source_queries in sources.items():
        desc = source_descriptions.get(source, source.replace("_", " ").title())
        print(f"  {Colors.BOLD}{desc}{Colors.RESET}", file=output)
        print(f"  {Colors.DIM}{'─' * 50}{Colors.RESET}", file=output)
        for q in source_queries:
            print(f"    • {q['question'][:60]}{'...' if len(q['question']) > 60 else ''}", file=output)
        print(file=output)

    # Triage Agent status
    if triage_available:
        print(f"  {Colors.GREEN}✓ Triage Agent available{Colors.RESET} - "
              f"Queries can be processed automatically", file=output)
    else:
        print(f"  {Colors.YELLOW}⚠ Triage Agent not configured{Colors.RESET} - "
              f"Manual routing required", file=output)
        print(f"    To enable: Ensure agents/triage.py is properly configured", file=output)


def print_safety_disclaimer(output) -> None:
    """Print the safety disclaimer section."""
    print(format_header("IMPORTANT SAFETY INFORMATION"), file=output)

    disclaimer = """
  This analysis is for EDUCATIONAL PURPOSES ONLY.

  • This tool does NOT provide medical advice
  • NEVER adjust insulin doses based solely on this analysis
  • ALWAYS discuss changes with your healthcare team
  • Patterns shown are observational and require clinical interpretation

  If you experience severe hypoglycemia or hyperglycemia,
  contact your healthcare provider or emergency services immediately.
"""
    print(f"{Colors.YELLOW}{disclaimer}{Colors.RESET}", file=output)


def print_next_steps(queries: list[dict], output) -> None:
    """Print suggested next steps."""
    print(format_subheader("SUGGESTED NEXT STEPS"), file=output)

    steps = [
        "Review this report with your diabetes care team",
        "Discuss detected patterns at your next appointment",
    ]

    if queries:
        top_query = queries[0]
        pattern = top_query.get("pattern_type", "").replace("_", " ")
        steps.append(f"Focus first on: {pattern}")

    steps.extend([
        "Continue logging meals and activities for better pattern detection",
        "Schedule a follow-up analysis in 2-4 weeks",
    ])

    print(file=output)
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step}", file=output)
    print(file=output)


def check_triage_agent() -> bool:
    """Check if Triage Agent is available and configured."""
    try:
        from agents import TriageAgent
        # Try to instantiate (will fail if not configured)
        agent = TriageAgent()
        return True
    except Exception:
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze Glooko data and generate personalized advice",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/analyze_and_advise.py
  python scripts/analyze_and_advise.py --file data/glooko/export.zip
  python scripts/analyze_and_advise.py --limit 3 --output report.txt

This script provides educational information only.
Always consult your healthcare team before making changes.
"""
    )

    parser.add_argument(
        "--file", "-f",
        type=Path,
        help="Path to Glooko export file (default: most recent in data/glooko/)"
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=5,
        help="Maximum number of research queries (default: 5)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Save report to file (default: print to screen)"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )

    args = parser.parse_args()

    # Setup output
    output = sys.stdout
    if args.output:
        try:
            output = open(args.output, "w", encoding="utf-8")
            Colors.disable()  # No colors in file output
        except IOError as e:
            print(f"Error: Cannot write to {args.output}: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.no_color:
        Colors.disable()

    try:
        # Import agents
        from agents import GlookoAnalyzer
        from agents.data_ingestion import generate_research_queries, ANALYSIS_DISCLAIMER

        # Find export file
        data_dir = PROJECT_ROOT / "data" / "glooko"

        if args.file:
            if not args.file.exists():
                print(f"Error: File not found: {args.file}", file=sys.stderr)
                sys.exit(1)
            export_file = args.file
        else:
            export_file = find_latest_export(data_dir)
            if not export_file:
                print(format_header("DIABETES BUDDY - ANALYSIS REPORT"), file=output)
                print(f"\n  {Colors.YELLOW}No Glooko export files found.{Colors.RESET}\n", file=output)
                print("  To get started:", file=output)
                print("    1. Export your data from Glooko (Settings > Export Data)", file=output)
                print("    2. Save the ZIP file to: data/glooko/", file=output)
                print("    3. Run this script again", file=output)
                print(f"\n  Data directory: {data_dir}\n", file=output)
                sys.exit(0)

        # Print header
        print(format_header("DIABETES BUDDY - PERSONALIZED ANALYSIS REPORT"), file=output)
        print(f"\n  {Colors.DIM}Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}", file=output)
        print(f"  {Colors.DIM}Source: {export_file.name}{Colors.RESET}", file=output)

        # Process the export
        print(f"\n  {Colors.CYAN}Analyzing your data...{Colors.RESET}", file=output)

        analyzer = GlookoAnalyzer(use_cache=True)
        results = analyzer.process_export(export_file)

        # Generate research queries
        queries = generate_research_queries(results, max_queries=args.limit)

        # Check Triage Agent availability
        triage_available = check_triage_agent()

        # Print report sections
        print_data_summary(results, output)
        print_detected_patterns(results, output)
        print_research_queries(queries, output)
        print_routing_plan(queries, triage_available, output)
        print_next_steps(queries, output)
        print_safety_disclaimer(output)

        # Footer
        print(f"\n{Colors.DIM}{'─' * 70}{Colors.RESET}", file=output)
        print(f"{Colors.DIM}  Report generated by Diabetes Buddy v1.0{Colors.RESET}", file=output)
        print(f"{Colors.DIM}  For questions, consult your healthcare team{Colors.RESET}", file=output)
        print(f"{Colors.DIM}{'─' * 70}{Colors.RESET}\n", file=output)

        if args.output:
            print(f"Report saved to: {args.output}", file=sys.stderr)

        sys.exit(0)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    except ValueError as e:
        print(f"Error: Invalid file format - {e}", file=sys.stderr)
        print("Make sure you're using a Glooko data export file.", file=sys.stderr)
        sys.exit(1)

    except ImportError as e:
        print(f"Error: Missing dependency - {e}", file=sys.stderr)
        print("Run: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    finally:
        if output != sys.stdout:
            output.close()


if __name__ == "__main__":
    main()
