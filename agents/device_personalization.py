"""Device personalization with regularized learning rate feedback."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.device_detection import anonymize_session_id
from agents.researcher_chromadb import SearchResult

logger = logging.getLogger(__name__)


@dataclass
class BoostAdjustmentState:
    """Track boost adjustment state for a user/device pair."""

    session_id_hash: str
    device_type: str  # 'pump' or 'cgm'
    manufacturer: str
    feedback_count: int = 0
    current_boost: float = 0.2
    last_adjusted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    adjustment_history: List[Dict[str, Any]] = field(default_factory=list)


class PersonalizationManager:
    """Apply device-specific boosts with regularized learning."""

    def __init__(self, base_dir: Optional[Path] = None, config: Optional[Dict[str, Any]] = None) -> None:
        self.base_dir = Path(base_dir or "data/users")
        self.config = config or {}
        personalization_config = self.config.get("personalization", {})
        self.device_priority_boost = float(personalization_config.get("device_priority_boost", 0.2))
        self.max_boost = float(personalization_config.get("max_boost", 0.3))
        self.base_learning_rate = float(personalization_config.get("learning_rate", 0.1))
        self.decay_factor = float(personalization_config.get("decay_factor", 0.1))

    def apply_device_boost(
        self,
        results: List[SearchResult],
        session_id: str,
        user_devices: Optional[Dict[str, Optional[str]]] = None,
    ) -> List[SearchResult]:
        """
        Apply +0.2 confidence boost to results matching user's pump/CGM.

        Args:
            results: SearchResult objects from knowledge retrieval
            session_id: User session ID
            user_devices: Optional dict with keys 'pump', 'cgm' and values like 'tandem', 'dexcom'

        Returns:
            Boosted results with confidence capped at 1.0
        """
        if not user_devices:
            return results

        boosted: List[SearchResult] = []
        for result in results:
            adjusted_confidence = result.confidence
            matched_device = None

            if user_devices.get("pump") and self._is_device_match(result.source, user_devices["pump"]):
                adjusted_confidence += self.device_priority_boost
                matched_device = f"pump:{user_devices['pump']}"
            elif user_devices.get("cgm") and self._is_device_match(result.source, user_devices["cgm"]):
                adjusted_confidence += self.device_priority_boost
                matched_device = f"cgm:{user_devices['cgm']}"

            adjusted_confidence = min(adjusted_confidence, 1.0)
            adjusted_confidence = max(adjusted_confidence, 0.0)

            new_result = SearchResult(
                quote=result.quote,
                page_number=result.page_number,
                confidence=adjusted_confidence,
                source=result.source,
                context=result.context,
            )
            if matched_device:
                logger.debug(f"Device boost applied: {matched_device} -> {result.confidence:.2f} -> {adjusted_confidence:.2f}")
            boosted.append(new_result)

        return boosted

    def calculate_effective_learning_rate(self, feedback_count: int) -> float:
        """
        Calculate effective learning rate with decay formula.

        Formula: effective_rate = base_rate / (1 + decay_factor * feedback_count)

        Examples:
        - feedback_count=0: 0.1 / 1 = 0.1000
        - feedback_count=1: 0.1 / 1.1 ≈ 0.0909
        - feedback_count=5: 0.1 / 1.5 ≈ 0.0667
        - feedback_count=10: 0.1 / 2.0 = 0.0500

        Args:
            feedback_count: Number of feedback events received

        Returns:
            Effective learning rate (0.0 to 0.1)
        """
        if feedback_count < 0:
            raise ValueError("feedback_count must be >= 0")
        denominator = 1.0 + self.decay_factor * feedback_count
        rate = self.base_learning_rate / denominator
        return rate

    def adjust_boost_from_feedback(
        self,
        session_id: str,
        device_type: str,
        manufacturer: str,
        feedback_delta: float,
    ) -> BoostAdjustmentState:
        """
        Adjust boost based on user feedback with regularized learning.

        Positive feedback_delta: Increase boost (up to max_boost).
        Negative feedback_delta: Decrease boost (floor at 0.0).
        Learning rate decays as feedback count increases.

        Args:
            session_id: User session ID
            device_type: 'pump' or 'cgm'
            manufacturer: Device manufacturer
            feedback_delta: Change amount (e.g., +0.05, -0.1)

        Returns:
            Updated BoostAdjustmentState
        """
        state = self._load_boost_state(session_id, device_type, manufacturer)
        if state is None:
            state = BoostAdjustmentState(
                session_id_hash=anonymize_session_id(session_id),
                device_type=device_type,
                manufacturer=manufacturer,
            )

        effective_rate = self.calculate_effective_learning_rate(state.feedback_count)
        old_boost = state.current_boost
        adjustment = effective_rate * feedback_delta
        new_boost = old_boost + adjustment
        new_boost = max(0.0, min(new_boost, self.max_boost))

        state.feedback_count += 1
        state.current_boost = new_boost
        state.last_adjusted_at = datetime.now(timezone.utc).isoformat()
        state.adjustment_history.append(
            {
                "timestamp": state.last_adjusted_at,
                "feedback_delta": feedback_delta,
                "effective_learning_rate": effective_rate,
                "old_boost": old_boost,
                "adjustment": adjustment,
                "new_boost": new_boost,
                "feedback_count": state.feedback_count,
            }
        )

        self._save_boost_state(state)
        logger.debug(
            f"Boost adjusted: {manufacturer} feedback={feedback_delta:.2f}, "
            f"effective_rate={effective_rate:.4f}, "
            f"{old_boost:.3f} -> {new_boost:.3f} (feedback_count={state.feedback_count})"
        )

        return state

    def _is_device_match(self, source_name: str, manufacturer: str) -> bool:
        """Check if source matches user's device manufacturer."""
        source_lower = (source_name or "").lower()
        manufacturer_lower = (manufacturer or "").lower()
        return manufacturer_lower in source_lower or source_lower in manufacturer_lower

    def _load_boost_state(self, session_id: str, device_type: str, manufacturer: str) -> Optional[BoostAdjustmentState]:
        """Load persisted boost state from JSON."""
        session_hash = anonymize_session_id(session_id)
        path = self._boost_state_path(session_hash, device_type, manufacturer)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return BoostAdjustmentState(
                session_id_hash=data["session_id_hash"],
                device_type=data["device_type"],
                manufacturer=data["manufacturer"],
                feedback_count=int(data.get("feedback_count", 0)),
                current_boost=float(data.get("current_boost", 0.2)),
                last_adjusted_at=data.get("last_adjusted_at", datetime.now(timezone.utc).isoformat()),
                adjustment_history=data.get("adjustment_history", []),
            )
        except Exception as exc:
            logger.warning(f"Failed to load boost state: {exc}")
            return None

    def _save_boost_state(self, state: BoostAdjustmentState) -> None:
        """Persist boost state to JSON."""
        path = self._boost_state_path(state.session_id_hash, state.device_type, state.manufacturer)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id_hash": state.session_id_hash,
            "device_type": state.device_type,
            "manufacturer": state.manufacturer,
            "feedback_count": state.feedback_count,
            "current_boost": state.current_boost,
            "last_adjusted_at": state.last_adjusted_at,
            "adjustment_history": state.adjustment_history,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _boost_state_path(self, session_hash: str, device_type: str, manufacturer: str) -> Path:
        """Construct path for boost state JSON file."""
        return self.base_dir / session_hash / f"boost_{device_type}_{manufacturer}.json"

    def learn_from_negative_feedback(
        self,
        query: str,
        response: str,
        sources: List[str],
        session_id: str,
        rag_quality: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Track query patterns that correlate with 'not-helpful' feedback.
        
        Logs patterns for analysis and adjusts retrieval strategy.
        
        Args:
            query: The user query
            response: The response that received negative feedback
            sources: List of sources used
            session_id: User session ID
            rag_quality: Optional RAG quality metrics
        """
        session_hash = anonymize_session_id(session_id)
        feedback_log_path = self.base_dir / session_hash / "negative_feedback.jsonl"
        feedback_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        feedback_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query[:200],  # Truncate for privacy
            "query_length": len(query),
            "response_length": len(response),
            "sources_used": sources,
            "rag_quality": rag_quality or {},
            "query_type": self._classify_query_type(query),
        }
        
        # Append to JSONL log
        try:
            with open(feedback_log_path, 'a') as f:
                f.write(json.dumps(feedback_entry) + '\n')
            logger.info(f"Logged negative feedback for session {session_hash[:8]}")
        except Exception as e:
            logger.error(f"Failed to log negative feedback: {e}")
    
    def _classify_query_type(self, query: str) -> str:
        """Classify query into broad categories for pattern tracking."""
        query_lower = query.lower()
        
        if any(word in query_lower for word in ['how', 'what', 'why', 'when', 'where']):
            return 'question'
        elif any(word in query_lower for word in ['configure', 'setup', 'install', 'set up']):
            return 'configuration'
        elif any(word in query_lower for word in ['error', 'problem', 'issue', 'not working']):
            return 'troubleshooting'
        elif any(word in query_lower for word in ['loop', 'openaps', 'androidaps', 'pump', 'cgm']):
            return 'device_specific'
        else:
            return 'general'
    
    def adjust_retrieval_strategy(
        self,
        query: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Return modified retrieval parameters based on historical performance.
        
        Analyzes negative feedback patterns to adjust top_k and min_confidence
        for better results on similar queries.
        
        Args:
            query: The current user query
            session_id: User session ID
            
        Returns:
            Dict with 'top_k', 'min_confidence', and 'reason' for adjustments
        """
        session_hash = anonymize_session_id(session_id)
        feedback_log_path = self.base_dir / session_hash / "negative_feedback.jsonl"
        
        # Default retrieval parameters
        strategy = {
            'top_k': 5,
            'min_confidence': 0.35,
            'reason': 'default'
        }
        
        if not feedback_log_path.exists():
            return strategy
        
        # Load recent negative feedback
        try:
            with open(feedback_log_path, 'r') as f:
                feedback_entries = [json.loads(line) for line in f]
        except Exception as e:
            logger.warning(f"Could not load feedback history: {e}")
            return strategy
        
        if not feedback_entries:
            return strategy
        
        # Analyze patterns
        query_type = self._classify_query_type(query)
        similar_feedback = [
            entry for entry in feedback_entries
            if entry.get('query_type') == query_type
        ]
        
        if len(similar_feedback) >= 2:
            # If this query type has received negative feedback, adjust strategy
            avg_rag_confidence = sum(
                entry.get('rag_quality', {}).get('avg_confidence', 0.7)
                for entry in similar_feedback
            ) / len(similar_feedback)
            
            if avg_rag_confidence < 0.5:
                # Low confidence RAG results led to negative feedback
                # Increase top_k to get more options, lower threshold
                strategy['top_k'] = 10
                strategy['min_confidence'] = 0.25
                strategy['reason'] = f'low_confidence_pattern_{query_type}'
                logger.info(f"Adjusted retrieval for {query_type}: top_k=10, min_conf=0.25")
            elif avg_rag_confidence > 0.8:
                # High confidence but still negative feedback
                # Maybe need more diverse sources
                strategy['top_k'] = 8
                strategy['min_confidence'] = 0.4
                strategy['reason'] = f'need_diversity_{query_type}'
                logger.info(f"Adjusted retrieval for {query_type}: top_k=8, min_conf=0.4")
        
        return strategy

