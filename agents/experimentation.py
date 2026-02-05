"""Experimentation module for A/B testing and cohort assignment."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


def anonymize_session_id(session_id: str) -> str:
    """Return deterministic SHA-256 hash for a session id."""
    if session_id is None:
        raise ValueError("session_id cannot be None")
    if not isinstance(session_id, str):
        session_id = str(session_id)
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return digest


@dataclass(frozen=True)
class CohortConfig:
    name: str
    cohorts: Dict[str, int]
    metrics: List[str] = field(default_factory=list)
    duration_days: int = 30
    min_sample_size: int = 620
    significance_threshold: float = 0.05

    def validate_split(self) -> None:
        total = sum(int(value) for value in self.cohorts.values())
        if total != 100:
            raise ValueError(f"Cohort split must equal 100, got {total}")

    def get_cohort_for_bucket(self, bucket: int) -> str:
        if bucket < 0 or bucket >= 100:
            raise ValueError("bucket must be in range [0, 99]")
        self.validate_split()
        cumulative = 0
        for cohort_name in sorted(self.cohorts.keys()):
            cumulative += int(self.cohorts[cohort_name])
            if bucket < cumulative:
                return cohort_name
        return sorted(self.cohorts.keys())[-1]

    def apply_control_constraints(self, rag_quality: Dict[str, Any], parametric_usage: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Apply control constraints for pure RAG behavior."""
        updated_rag = dict(rag_quality)
        updated_rag["min_chunks"] = max(int(updated_rag.get("min_chunks", 3)), 3)
        updated_parametric = dict(parametric_usage)
        updated_parametric["max_ratio"] = 0.0
        updated_parametric["confidence_score"] = 0.0
        return updated_rag, updated_parametric


@dataclass
class ExperimentAssignment:
    session_id_hash: str
    cohort: str
    experiment: str
    query: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ExperimentManager:
    """Manage A/B experimentation configuration and logging."""

    def __init__(self, config: Dict[str, Any], storage_dir: Optional[Path] = None) -> None:
        self.config = config or {}
        self.enabled = bool(self.config.get("experimentation", {}).get("enabled", False))
        self.experiments = self._load_experiments(self.config.get("experimentation", {}))
        self.storage_dir = Path(storage_dir or self.config.get("experimentation", {}).get("storage_dir", "data"))

    def _load_experiments(self, experimentation_config: Dict[str, Any]) -> Dict[str, CohortConfig]:
        experiments = {}
        for exp in experimentation_config.get("experiments", []):
            cohort_config = CohortConfig(
                name=exp.get("name", "hybrid_vs_pure_rag"),
                cohorts=exp.get("cohorts", {"control": 50, "treatment": 50}),
                metrics=list(exp.get("metrics", [])),
                duration_days=int(exp.get("duration_days", 30)),
                min_sample_size=int(exp.get("min_sample_size", 620)),
                significance_threshold=float(exp.get("significance_threshold", 0.05)),
            )
            cohort_config.validate_split()
            experiments[cohort_config.name] = cohort_config
        return experiments

    def get_cohort_assignment(self, session_id: str, experiment_name: str = "hybrid_vs_pure_rag") -> str:
        cohort_config = self.experiments.get(experiment_name)
        if cohort_config is None:
            cohort_config = CohortConfig(
                name=experiment_name,
                cohorts={"control": 50, "treatment": 50},
            )
        session_hash = anonymize_session_id(session_id)
        bucket = int(session_hash[:8], 16) % 100
        cohort = cohort_config.get_cohort_for_bucket(bucket)
        return cohort

    def log_assignment(
        self,
        session_id: str,
        query: str,
        cohort: str,
        experiment_name: str = "hybrid_vs_pure_rag",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExperimentAssignment:
        session_hash = anonymize_session_id(session_id)
        assignment = ExperimentAssignment(
            session_id_hash=session_hash,
            cohort=cohort,
            experiment=experiment_name,
            query=query,
            metadata=metadata or {},
        )
        self._write_assignment(assignment)
        return assignment

    def _write_assignment(self, assignment: ExperimentAssignment) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.storage_dir / "ab_test_assignments.csv"
        file_exists = path.exists()
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "created_at",
                    "session_id_hash",
                    "experiment",
                    "cohort",
                    "query",
                    "metadata",
                ],
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(
                {
                    "created_at": assignment.created_at,
                    "session_id_hash": assignment.session_id_hash,
                    "experiment": assignment.experiment,
                    "cohort": assignment.cohort,
                    "query": assignment.query,
                    "metadata": json.dumps(assignment.metadata, ensure_ascii=False),
                }
            )

    def validate_split(self, experiment_name: str = "hybrid_vs_pure_rag") -> None:
        cohort_config = self.experiments.get(experiment_name)
        if cohort_config is None:
            raise ValueError(f"Experiment '{experiment_name}' not configured")
        cohort_config.validate_split()
