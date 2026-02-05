"""Analytics for A/B testing experiments with statistical rigor."""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from scipy import stats
except ImportError:
    stats = None

logger = logging.getLogger(__name__)


@dataclass
class ExperimentStatistics:
    """Statistical summary of A/B test results."""

    experiment_name: str
    control_n: int
    treatment_n: int
    control_helpful_rate: float
    treatment_helpful_rate: float
    min_sample_size: int
    min_sample_size_reached: bool
    p_value: Optional[float] = None
    t_statistic: Optional[float] = None
    cohens_d: Optional[float] = None
    is_significant: bool = False
    effect_size_category: str = "negligible"
    winner: Optional[str] = None  # 'control', 'treatment', or None
    recommendation: str = ""


class ExperimentAnalytics:
    """Analyze A/B test data with statistical testing."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = Path(data_dir or "data")
        self.assignments_file = self.data_dir / "ab_test_assignments.csv"
        self.feedback_file = self.data_dir / "feedback.csv"

    def get_experiment_status(self, experiment_name: str = "hybrid_vs_pure_rag", min_sample_size: int = 620) -> ExperimentStatistics:
        """Fetch live experiment statistics with t-test and effect size."""
        assignments = self._load_assignments()
        feedback = self._load_feedback()

        control_sessions = set(
            a["session_id_hash"]
            for a in assignments
            if a.get("experiment") == experiment_name and a.get("cohort") == "control"
        )
        treatment_sessions = set(
            a["session_id_hash"]
            for a in assignments
            if a.get("experiment") == experiment_name and a.get("cohort") == "treatment"
        )

        control_feedback = [
            f for f in feedback if f.get("session_id_hash") in control_sessions
        ]
        treatment_feedback = [
            f for f in feedback if f.get("session_id_hash") in treatment_sessions
        ]

        control_n = len(control_feedback)
        treatment_n = len(treatment_feedback)

        control_helpful = sum(1 for f in control_feedback if f.get("feedback") == "helpful")
        treatment_helpful = sum(1 for f in treatment_feedback if f.get("feedback") == "helpful")

        control_rate = control_helpful / control_n if control_n > 0 else 0.0
        treatment_rate = treatment_helpful / treatment_n if treatment_n > 0 else 0.0

        min_size_reached = control_n >= min_sample_size and treatment_n >= min_sample_size

        p_value = None
        t_statistic = None
        cohens_d = None
        is_significant = False
        effect_size = "negligible"
        winner = None

        if min_size_reached and stats is not None:
            p_value, t_statistic, cohens_d = self._compute_statistics(
                control_helpful, control_n, treatment_helpful, treatment_n
            )
            is_significant = (p_value or 1.0) < 0.05
            effect_size = self._categorize_effect_size(cohens_d or 0.0)

            if is_significant:
                if treatment_rate > control_rate:
                    winner = "treatment"
                elif control_rate > treatment_rate:
                    winner = "control"

        stats_obj = ExperimentStatistics(
            experiment_name=experiment_name,
            control_n=control_n,
            treatment_n=treatment_n,
            control_helpful_rate=round(control_rate, 3),
            treatment_helpful_rate=round(treatment_rate, 3),
            min_sample_size=min_sample_size,
            min_sample_size_reached=min_size_reached,
            p_value=round(p_value, 4) if p_value else None,
            t_statistic=round(t_statistic, 3) if t_statistic else None,
            cohens_d=round(cohens_d, 3) if cohens_d else None,
            is_significant=is_significant,
            effect_size_category=effect_size,
            winner=winner,
        )

        stats_obj.recommendation = self._generate_recommendation(stats_obj)
        return stats_obj

    def _load_assignments(self) -> List[Dict[str, Any]]:
        """Load all cohort assignments."""
        if not self.assignments_file.exists():
            return []
        rows = []
        try:
            with self.assignments_file.open("r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    if row:
                        rows.append(row)
        except Exception as exc:
            logger.warning(f"Failed to load assignments: {exc}")
        return rows

    def _load_feedback(self) -> List[Dict[str, Any]]:
        """Load all feedback entries."""
        if not self.feedback_file.exists():
            return []
        rows = []
        try:
            with self.feedback_file.open("r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    if row:
                        rows.append(row)
        except Exception as exc:
            logger.warning(f"Failed to load feedback: {exc}")
        return rows

    @staticmethod
    def _compute_statistics(
        control_successes: int,
        control_n: int,
        treatment_successes: int,
        treatment_n: int,
    ) -> Tuple[float, float, float]:
        """Compute t-test and Cohen's d for binary outcomes."""
        if not stats:
            return 1.0, 0.0, 0.0

        control_rate = control_successes / control_n if control_n > 0 else 0.0
        treatment_rate = treatment_successes / treatment_n if treatment_n > 0 else 0.0

        control_se = (control_rate * (1 - control_rate) / control_n) ** 0.5 if control_n > 0 else 0.0
        treatment_se = (
            (treatment_rate * (1 - treatment_rate) / treatment_n) ** 0.5 if treatment_n > 0 else 0.0
        )

        pooled_se = (control_se**2 + treatment_se**2) ** 0.5
        if pooled_se > 0:
            t_stat = (treatment_rate - control_rate) / pooled_se
        else:
            t_stat = 0.0

        df = control_n + treatment_n - 2
        p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df)) if df > 0 else 1.0

        pooled_std = (
            (
                (control_n - 1) * control_rate * (1 - control_rate)
                + (treatment_n - 1) * treatment_rate * (1 - treatment_rate)
            )
            / (control_n + treatment_n - 2)
        ) ** 0.5
        if pooled_std > 0:
            cohens_d = (treatment_rate - control_rate) / pooled_std
        else:
            cohens_d = 0.0

        return p_val, t_stat, cohens_d

    @staticmethod
    def _categorize_effect_size(cohens_d: float) -> str:
        """Categorize Cohen's d as per standard conventions."""
        abs_d = abs(cohens_d)
        if abs_d < 0.2:
            return "negligible"
        elif abs_d < 0.5:
            return "small"
        elif abs_d < 0.8:
            return "medium"
        else:
            return "large"

    @staticmethod
    def _generate_recommendation(stats_obj: ExperimentStatistics) -> str:
        """Generate actionable recommendation based on statistics."""
        if not stats_obj.min_sample_size_reached:
            remaining_control = max(0, stats_obj.min_sample_size - stats_obj.control_n)
            remaining_treatment = max(0, stats_obj.min_sample_size - stats_obj.treatment_n)
            return (
                f"Collecting data. Need {remaining_control} more control, "
                f"{remaining_treatment} more treatment samples."
            )

        if not stats_obj.is_significant:
            return "No statistical significance detected (p >= 0.05). Continue experiment."

        if stats_obj.winner == "treatment":
            effect_text = f"{(stats_obj.treatment_helpful_rate - stats_obj.control_helpful_rate) * 100:.1f}%"
            return (
                f"✅ WINNER: Treatment (hybrid RAG+parametric) improved helpful rate by {effect_text}. "
                f"Ready to roll out (p={stats_obj.p_value})."
            )
        elif stats_obj.winner == "control":
            return (
                f"⚠️ Control outperforms treatment. Consider reverting to pure RAG "
                f"(p={stats_obj.p_value})."
            )

        return "Experiment in progress."
