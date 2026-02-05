import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.analytics import ExperimentAnalytics, ExperimentStatistics


def test_compute_statistics():
    """Test statistical calculations for binary outcomes."""
    analytics = ExperimentAnalytics()
    
    # Case 1: Equal rates (should be non-significant)
    p_val, t_stat, cohens_d = analytics._compute_statistics(
        control_successes=50, control_n=100,
        treatment_successes=50, treatment_n=100,
    )
    assert p_val > 0.05  # Not significant
    assert abs(cohens_d) < 0.1  # Negligible effect

    # Case 2: 5% absolute difference (treatment better)
    p_val, t_stat, cohens_d = analytics._compute_statistics(
        control_successes=70, control_n=100,
        treatment_successes=75, treatment_n=100,
    )
    assert 0.0 <= p_val <= 1.0
    assert cohens_d > 0  # Positive effect


def test_effect_size_categorization():
    """Test Cohen's d categorization."""
    assert ExperimentAnalytics._categorize_effect_size(0.1) == "negligible"
    assert ExperimentAnalytics._categorize_effect_size(0.3) == "small"
    assert ExperimentAnalytics._categorize_effect_size(0.6) == "medium"
    assert ExperimentAnalytics._categorize_effect_size(0.9) == "large"


def test_recommendation_generation_insufficient_data(tmp_path: Path):
    """Test recommendation when data is insufficient."""
    analytics = ExperimentAnalytics(data_dir=tmp_path)
    
    stats = ExperimentStatistics(
        experiment_name="hybrid_vs_pure_rag",
        control_n=100,
        treatment_n=100,
        control_helpful_rate=0.70,
        treatment_helpful_rate=0.75,
        min_sample_size=620,
        min_sample_size_reached=False,
    )
    stats.recommendation = analytics._generate_recommendation(stats)
    
    assert "Collecting data" in stats.recommendation
    assert "need" in stats.recommendation.lower()


def test_recommendation_generation_treatment_winner(tmp_path: Path):
    """Test recommendation when treatment is winner."""
    analytics = ExperimentAnalytics(data_dir=tmp_path)
    
    stats = ExperimentStatistics(
        experiment_name="hybrid_vs_pure_rag",
        control_n=650,
        treatment_n=650,
        control_helpful_rate=0.70,
        treatment_helpful_rate=0.75,
        min_sample_size=620,
        min_sample_size_reached=True,
        p_value=0.02,
        is_significant=True,
        winner="treatment",
    )
    stats.recommendation = analytics._generate_recommendation(stats)
    
    assert "WINNER" in stats.recommendation
    assert "treatment" in stats.recommendation.lower()
    assert "5.0%" in stats.recommendation
