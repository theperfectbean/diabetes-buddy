import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.experimentation import ExperimentManager, anonymize_session_id


def test_anonymize_session_id_deterministic():
    first = anonymize_session_id("session-123")
    second = anonymize_session_id("session-123")
    assert first == second
    assert len(first) == 64
    assert all(ch in "0123456789abcdef" for ch in first)


def test_cohort_assignment_deterministic():
    config = {
        "experimentation": {
            "experiments": [
                {
                    "name": "hybrid_vs_pure_rag",
                    "cohorts": {"control": 50, "treatment": 50},
                }
            ]
        }
    }
    manager = ExperimentManager(config)
    cohort_a = manager.get_cohort_assignment("session-abc")
    cohort_b = manager.get_cohort_assignment("session-abc")
    assert cohort_a == cohort_b
    assert cohort_a in {"control", "treatment"}


def test_log_assignment_uses_hash(tmp_path: Path):
    config = {
        "experimentation": {
            "experiments": [
                {
                    "name": "hybrid_vs_pure_rag",
                    "cohorts": {"control": 50, "treatment": 50},
                }
            ]
        }
    }
    manager = ExperimentManager(config, storage_dir=tmp_path)
    cohort = manager.get_cohort_assignment("session-xyz")
    manager.log_assignment("session-xyz", "query", cohort)

    assignments_path = tmp_path / "ab_test_assignments.csv"
    assert assignments_path.exists()
    with assignments_path.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert rows[0]["session_id_hash"] == anonymize_session_id("session-xyz")
    assert "session-xyz" not in rows[0]["session_id_hash"]


def test_validate_split_error():
    config = {
        "experimentation": {
            "experiments": [
                {
                    "name": "hybrid_vs_pure_rag",
                    "cohorts": {"control": 40, "treatment": 50},
                }
            ]
        }
    }
    with pytest.raises(ValueError):
        ExperimentManager(config)
