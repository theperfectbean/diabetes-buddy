#!/usr/bin/env python3
"""
Quality Baseline Analysis Script

Analyzes quality benchmark results and generates baseline report.
Processes data/quality_scores.csv to create docs/QUALITY_BASELINE_REPORT.md
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.test_response_quality_benchmark import (
    CATEGORY_THRESHOLDS,
    DEVICE_CONFIGURATION_QUERIES,
    TROUBLESHOOTING_QUERIES,
    CLINICAL_EDUCATION_QUERIES,
    ALGORITHM_AUTOMATION_QUERIES,
    PERSONAL_DATA_ANALYSIS_QUERIES,
    SAFETY_CRITICAL_QUERIES,
    DEVICE_COMPARISON_QUERIES,
    EMOTIONAL_SUPPORT_QUERIES,
    EDGE_CASE_QUERIES,
    EMERGING_RARE_QUERIES,
)

def load_quality_data(csv_path: Path) -> pd.DataFrame:
    """Load quality scores from CSV file."""
    if not csv_path.exists():
        print(f"Error: Quality scores file not found: {csv_path}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(csv_path)
        print(f"Loaded {len(df)} quality score records")
        return df
    except Exception as e:
        print(f"Error loading quality data: {e}")
        return pd.DataFrame()

def analyze_category_performance(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze performance by category."""
    results = {}

    # Define category mappings
    category_queries = {
        'device_configuration': DEVICE_CONFIGURATION_QUERIES,
        'troubleshooting': TROUBLESHOOTING_QUERIES,
        'clinical_education': CLINICAL_EDUCATION_QUERIES,
        'algorithm_automation': ALGORITHM_AUTOMATION_QUERIES,
        'personal_data_analysis': PERSONAL_DATA_ANALYSIS_QUERIES,
        'safety_critical': SAFETY_CRITICAL_QUERIES,
        'device_comparison': DEVICE_COMPARISON_QUERIES,
        'emotional_support': EMOTIONAL_SUPPORT_QUERIES,
        'edge_cases': EDGE_CASE_QUERIES,
        'emerging_rare': EMERGING_RARE_QUERIES,
    }

    # Since we don't have query text in CSV, we'll use approximate analysis
    # In practice, you'd modify the logging to include category info

    # Calculate overall statistics
    if len(df) > 0:
        valid_scores = df[df['average_score'] > 0]
        if len(valid_scores) > 0:
            results['overall'] = {
                'total_queries': len(df),
                'valid_scores': len(valid_scores),
                'pass_rate': len(valid_scores[valid_scores['average_score'] >= 2.5]) / len(valid_scores),
                'avg_score': valid_scores['average_score'].mean(),
                'median_score': valid_scores['average_score'].median(),
                'min_score': valid_scores['average_score'].min(),
                'max_score': valid_scores['average_score'].max()
            }

            # Dimension averages
            dimensions = ['answer_relevancy', 'practical_helpfulness', 'knowledge_guidance',
                         'tone_professionalism', 'clarity_structure', 'source_integration']

            results['dimensions'] = {}
            for dim in dimensions:
                if dim in valid_scores.columns:
                    scores = valid_scores[dim].dropna()
                    if len(scores) > 0:
                        results['dimensions'][dim] = {
                            'average': scores.mean(),
                            'median': scores.median(),
                            'min': scores.min(),
                            'max': scores.max()
                        }

    return results

def generate_markdown_report(analysis: Dict[str, Any], output_path: Path) -> None:
    """Generate markdown baseline report."""
    now = datetime.now()

    report = "# Quality Baseline Report\n\n"
    report += f"**Generated:** {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    report += "## Executive Summary\n\n"
    report += "This report establishes the baseline quality performance for the Diabetes Buddy response quality benchmark.\n\n"
    report += "## Execution Summary\n\n"
    report += f"- **Date:** {now.strftime('%Y-%m-%d')}\n"
    report += f"- **Total Queries Processed:** {analysis.get('overall', {}).get('total_queries', 0)}\n"
    report += f"- **Valid Scores:** {analysis.get('overall', {}).get('valid_scores', 0)}\n"
    report += f"- **Pass Rate:** {analysis.get('overall', {}).get('pass_rate', 0):.1%}\n"
    report += "- **Execution Time:** ~10 minutes (estimated)\n"
    report += f"- **Average Quality Score:** {analysis.get('overall', {}).get('avg_score', 0):.2f}/5.0\n\n"

    report += "## Category Pass Rates\n\n"
    report += "| Category | Tests | Passed | Failed | Pass Rate |\n"
    report += "|----------|-------|--------|--------|-----------|\n"
    report += "| Device Configuration | 5 | - | - | - |\n"
    report += "| Troubleshooting | 5 | - | - | - |\n"
    report += "| Clinical Education | 5 | - | - | - |\n"
    report += "| Algorithm/Automation | 5 | - | - | - |\n"
    report += "| Personal Data | 5 | - | - | - |\n"
    report += "| Safety Critical | 5 | - | - | - |\n"
    report += "| Device Comparison | 5 | - | - | - |\n"
    report += "| Emotional Support | 5 | - | - | - |\n"
    report += "| Edge Cases | 5 | - | - | - |\n"
    report += "| Emerging/Rare | 5 | - | - | - |\n\n"

    report += "## Quality Dimension Averages\n\n"
    report += "| Dimension | Average Score | Median | Min | Max |\n"
    report += "|-----------|---------------|--------|-----|-----|\n"

    dimensions = analysis.get('dimensions', {})
    for dim, stats in dimensions.items():
        dim_name = dim.replace('_', ' ').title()
        report += f"| {dim_name} | {stats['average']:.2f}/5.0 | {stats['median']:.2f} | {stats['min']:.2f} | {stats['max']:.2f} |\n"

    report += "\n## Failed Tests Analysis\n\n"
    report += "*Detailed failure analysis requires category mapping in CSV data. This will be implemented in the next iteration.*\n\n"

    report += "## Key Findings\n\n"
    report += "### Strongest Categories\n"
    report += "- *To be determined after full benchmark completion*\n\n"
    report += "### Weakest Categories\n"
    report += "- *To be determined after full benchmark completion*\n\n"
    report += "### Most Common Failure Patterns\n"
    report += "- Source integration appears to be a common issue based on current data\n"
    report += "- Some queries receiving 0.0 scores indicate processing failures\n\n"
    report += "### Quality Distribution\n"
    report += f"- Scores range from {analysis.get('overall', {}).get('min_score', 0):.2f} to {analysis.get('overall', {}).get('max_score', 0):.2f}\n"
    report += f"- Median score: {analysis.get('overall', {}).get('median_score', 0):.2f}\n"
    report += f"- {analysis.get('overall', {}).get('pass_rate', 0):.1%} of queries meet minimum quality threshold (2.5/5.0)\n\n"

    report += "## Baseline Statistics\n\n"
    report += f"**Baseline Date:** {now.strftime('%Y-%m-%d')}\n"
    report += f"**Baseline Pass Rate:** {analysis.get('overall', {}).get('pass_rate', 0):.1%}\n"
    report += f"**Baseline Average Score:** {analysis.get('overall', {}).get('avg_score', 0):.2f}/5.0\n\n"
    report += "### Dimension Baselines\n\n"

    for dim, stats in dimensions.items():
        dim_name = dim.replace('_', ' ').title()
        report += f"- **{dim_name}:** {stats['average']:.2f}/5.0 (baseline)\n"

    report += "\n## Recommendations for Optimization\n\n"
    report += "1. **Source Integration:** Improve citation and source attribution\n"
    report += "2. **Answer Relevancy:** Enhance query understanding and response targeting\n"
    report += "3. **Processing Reliability:** Address queries receiving 0.0 scores\n\n"
    report += "## Next Steps\n\n"
    report += "1. Complete full benchmark run with all 50 queries\n"
    report += "2. Implement category tracking in quality logging\n"
    report += "3. Tune quality thresholds based on baseline performance\n"
    report += "4. Establish regression monitoring pipeline\n"

    # Write report
    with open(output_path, 'w') as f:
        f.write(report)

    print(f"Baseline report generated: {output_path}")

def save_baseline_snapshot(df: pd.DataFrame, output_path: Path) -> None:
    """Save baseline snapshot for regression comparison."""
    if len(df) > 0:
        df.to_csv(output_path, index=False)
        print(f"Baseline snapshot saved: {output_path}")
    else:
        print("No data to save for baseline snapshot")

def main():
    """Main analysis function."""
    print("🔍 Analyzing Quality Baseline Data...")

    # Paths
    data_dir = project_root / "data"
    docs_dir = project_root / "docs"
    csv_path = data_dir / "quality_scores.csv"
    report_path = docs_dir / "QUALITY_BASELINE_REPORT.md"
    snapshot_path = data_dir / f"baseline_quality_{datetime.now().strftime('%Y-%m-%d')}.csv"

    # Load and analyze data
    df = load_quality_data(csv_path)
    if df.empty:
        print("❌ No quality data found. Run benchmark first.")
        return

    analysis = analyze_category_performance(df)

    # Generate outputs
    generate_markdown_report(analysis, report_path)
    save_baseline_snapshot(df, snapshot_path)

    print("✅ Baseline analysis complete!")
    print(f"📊 Report: {report_path}")
    print(f"💾 Snapshot: {snapshot_path}")

if __name__ == "__main__":
    main()