import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.analytics import ExperimentAnalytics
from agents.experimentation import ExperimentManager


def test_experiment_status_integration(tmp_path: Path):
    """Test full experiment status flow with real data."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    experiment_config = {
        "experimentation": {
            "enabled": True,
            "experiments": [
                {
                    "name": "hybrid_vs_pure_rag",
                    "cohorts": {"control": 50, "treatment": 50},
                    "min_sample_size": 10,
                }
            ]
        }
    }

    exp_mgr = ExperimentManager(experiment_config, storage_dir=data_dir)
    analytics = ExperimentAnalytics(data_dir=data_dir)

    cohort_control = exp_mgr.get_cohort_assignment("session-001")
    cohort_treatment = exp_mgr.get_cohort_assignment("session-abc")

    exp_mgr.log_assignment("session-001", "query1", cohort_control)
    exp_mgr.log_assignment("session-abc", "query1", cohort_treatment)

    feedback_file = data_dir / "feedback.csv"
    feedback_file.parent.mkdir(parents=True, exist_ok=True)

    import csv

    with feedback_file.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "session_id_hash",
                "feedback",
                "primary_source_type",
                "response_time_ms",
            ],
        )
        writer.writeheader()
        from agents.experimentation import anonymize_session_id

        for i in range(8):
            session = "session-001" if i < 5 else "session-abc"
            feedback = "helpful" if (i < 4 or i >= 6) else "not-helpful"
            writer.writerow(
                {
                    "timestamp": "2026-02-02T00:00:00+00:00",
                    "session_id_hash": anonymize_session_id(session),
                    "feedback": feedback,
                    "primary_source_type": "rag",
                    "response_time_ms": "1200",
                }
            )

    stats = analytics.get_experiment_status(
        experiment_name="hybrid_vs_pure_rag", min_sample_size=10
    )

    assert stats.control_n > 0 or stats.treatment_n > 0
    assert 0.0 <= stats.control_helpful_rate <= 1.0
    assert 0.0 <= stats.treatment_helpful_rate <= 1.0


def test_cohort_determinism_consistency(tmp_path: Path):
    """Test that cohort assignment is deterministic across manager instances."""
    config = {
        "experimentation": {
            "experiments": [
                {"name": "hybrid_vs_pure_rag", "cohorts": {"control": 50, "treatment": 50}}
            ]
        }
    }

    mgr1 = ExperimentManager(config, storage_dir=tmp_path / "mgr1")
    mgr2 = ExperimentManager(config, storage_dir=tmp_path / "mgr2")

    for session_id in ["session-001", "session-002", "session-abc"]:
        cohort1 = mgr1.get_cohort_assignment(session_id)
        cohort2 = mgr2.get_cohort_assignment(session_id)
        assert cohort1 == cohort2, f"Cohort mismatch for {session_id}"
