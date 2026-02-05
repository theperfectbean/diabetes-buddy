"""
Safety tier classification for Diabetes Buddy.

Implements a four-tier, evidence-graded safety model:
1) Evidence-based education
2) Personalized analysis with small, testable adjustments
3) Clinical decision deferral
4) Dangerous advice block
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SafetyTier(Enum):
    """Evidence-graded safety tiers."""
    TIER_1 = "tier_1_education"
    TIER_2 = "tier_2_personalized"
    TIER_3 = "tier_3_clinical"
    TIER_4 = "tier_4_dangerous"


class TierAction(Enum):
    """Action to take for a tier decision."""
    ALLOW = "allow"
    DEFER = "defer"
    BLOCK = "block"


@dataclass
class TierDecision:
    """Tier decision with safety action and messaging."""
    tier: SafetyTier
    action: TierAction
    reason: str
    disclaimer: str
    override_response: Optional[str] = None
    evidence_tags: Optional[list[str]] = None


class SafetyTierClassifier:
    """Classify a query/response into a safety tier."""

    # LLM provider for intent classification (optional, injected)
    _llm_provider = None

    DANGEROUS_PATTERNS = [
        # Match imperative instructions to skip/stop insulin (not descriptions)
        r"\b(you should|I recommend|please|make sure to|be sure to|don't forget to)\s+.{0,20}(skip|stop|discontinue)\s+(your\s+)?(insulin|medication|meds)\b",
        r"\b(skip|stop|discontinue)\s+(your\s+|taking\s+)?(insulin|medication|meds)\b(?!\s+(delivery|if|when|because))",  # Don't match "stop insulin delivery" or "stop insulin if..."
        r"\b(do\s+not|don't|never)\s+(take|use|inject)\s+(your\s+)?(insulin|medication|meds)\b",
        r"\b(overdose|double\s+dose|extra\s+dose)\b",
        r"\bstack(ing)?\s+(insulin|doses?|bolus(es)?)\b",
        r"\b(do\s+not|don't|never)\s+(take|use|inject)\s+(insulin|medication)\b",
    ]

    # Patterns for queries asking for specific dose calculations (BLOCK)
    DOSING_REQUEST_PATTERNS = [
        r"\bhow much insulin\s+(should|do|to)\b",
        r"\bwhat dose\s+(should|do|of)\b",
        r"\bcalculate\s+(my\s+)?bolus\b",
        r"\binsulin\s+dose\s+for\b",
        r"\bunits?\s+(for|to cover)\b",
    ]

    # Patterns for legitimate educational/strategy queries (ALLOW - check first)
    EDUCATIONAL_STRATEGY_PATTERNS = [
        # Strategy questions
        r"\bwhat\s+strateg(y|ies)\b",
        r"\bways?\s+to\s+(improve|reduce|fix|address|manage|handle|mitigate|account)\b",
        r"\bhow\s+(can|do|should)\s+I\s+(improve|reduce|fix|address|manage|handle|mitigate|account)\b",
        r"\bhow\s+to\s+(improve|reduce|fix|address|manage|handle|mitigate|account)\b",
        r"\bwhat\s+(can|should)\s+I\s+do\s+(about|for)\b",
        r"\btips?\s+(for|to|on)\b",
        r"\bhelp\s+(with|me)\b",
        # Meal management questions
        r"\b(slow[\s\-]?carb|high[\s\-]?fat|complex\s+carb|protein[\s\-]?rich|fast\s+carb)\b",
        r"\b(meals?|food|eat|eating)\s+(strategies|tips|handling|management|approach)\b",
        r"\b(pizza|pasta|fat|fiber|delayed|spike|absorption|glucose|meal)\b.*\b(account|handle|manage|deal|strategy)\b",
        # Common diabetes management topics (not dosing)
        r"\bdawn\s+phenomenon\b",
        r"\btime\s+in\s+range\b",
        r"\b(high|low)\s+(at night|overnight|morning|after meals?)\b",
        r"\bpattern(s)?\s+(analysis|review|management)\b",
        r"\bbasal\s+(testing|adjustment|optimization)\b",
        r"\bwhat\s+to\s+discuss\s+with\b",
        r"\bquestions?\s+(for|to ask)\s+(my\s+)?(doctor|endo|team|provider)\b",
    ]

    # Clinical decision patterns - more specific to prescriptive language
    # These should match directive/prescriptive statements, not educational mentions
    CLINICAL_DECISION_PATTERNS = [
        # Query asking to stop/change medications (includes common diabetes meds)
        r"\b(can|should)\s+I\s+(stop|discontinue|pause|quit|change|switch)\s+(my\s+)?(insulin|medication|meds?|metformin|glipizide|glyburide|januvia|ozempic|trulicity|jardiance|farxiga|invokana)\b",
        # Generic "stop/change my [medicine]" pattern
        r"\b(stop|discontinue|quit|change|switch)\s+my\s+\w+(in|ide|ity|iga|ana)\b",  # catches drug name suffixes
        # Prescriptive medication advice in responses
        r"\b(you\s+should|I\s+recommend)\s+(stop|discontinue|pause|quit|start|begin|switch|change)\s+(your\s+)?(insulin|medication|meds?)\b",
        # Pregnancy/surgery + medication adjustments
        r"\b(pregnancy|pregnant|surgery|procedure)\b.*\b(insulin|medication|dose)\b",
    ]

    EVIDENCE_MARKERS = [
        r"\b(ADA|American Diabetes Association)\b",
        r"\b(OpenAPS|Loop|AndroidAPS)\b",
        r"\b(device manual|user manual|manufacturer)\b",
        r"\b(documentation|guidelines|standards)\b",
    ]

    PERSONAL_DATA_MARKERS = [
        r"\b(your data|your glucose|your readings|your log)\b",
        r"\b(time in range|TIR|hourly|pattern)\b",
        r"\b(glooko)\b",
    ]

    TESTING_MARKERS = [
        r"\b(test|recheck|check|monitor|confirm|verify|track)\b",
        r"\b(fingerstick|meter|CGM)\b",
    ]

    A1C_PATTERN = re.compile(r"\b(a1c|hba1c)\b[^\d]*(\d+(?:\.\d+)?)", re.IGNORECASE)
    UNITS_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*(u|units?)\b", re.IGNORECASE)
    # Match percentages like "10%", "5 %" - trailing \b removed since % is not a word char
    PERCENT_PATTERN = re.compile(r"\b(\d{1,2})\s*%")

    def __init__(self, llm_provider=None):
        """
        Initialize safety tier classifier.
        
        Args:
            llm_provider: Optional LLM provider for intent classification fallback
        """
        if llm_provider:
            SafetyTierClassifier._llm_provider = llm_provider

    def classify(
        self,
        query: str,
        response_text: str,
        sources_used: Optional[list[str]] = None,
        rag_quality: Optional[dict] = None,
        glooko_available: bool = False,
    ) -> TierDecision:
        sources_used = sources_used or []
        rag_quality = rag_quality or {}

        query_lower = (query or "").lower()
        response_lower = (response_text or "").lower()

        # FIRST: Check if this is a legitimate educational/strategy query
        # These should be ALLOWED even if response mentions "adjust" or "dose" educationally
        is_educational_query = self._is_educational_strategy_query(query_lower)

        # Tier 4: dangerous advice (always block regardless of query type)
        if self._contains_dangerous_advice(query_lower, response_lower):
            return TierDecision(
                tier=SafetyTier.TIER_4,
                action=TierAction.BLOCK,
                reason="Potentially dangerous instruction detected (e.g., skipping medication or unsafe dosing).",
                disclaimer=self._tier_disclaimer(SafetyTier.TIER_4),
                override_response=self._tier4_block_message(),
                evidence_tags=[],
            )

        # Block specific dosing requests (query asks for dose calculation)
        if self._is_dosing_request(query_lower):
            return TierDecision(
                tier=SafetyTier.TIER_4,
                action=TierAction.BLOCK,
                reason="Specific dose calculation requests require clinician oversight.",
                disclaimer=self._tier_disclaimer(SafetyTier.TIER_4),
                override_response=self._dosing_defer_message(),
                evidence_tags=[],
            )

        # Block specific units in response ONLY if not an educational query
        # Educational queries can mention units in context (e.g., "typical ranges are...")
        if not is_educational_query and self._contains_specific_units(response_text):
            return TierDecision(
                tier=SafetyTier.TIER_4,
                action=TierAction.BLOCK,
                reason="Specific insulin dosing detected, which can be unsafe without clinician oversight.",
                disclaimer=self._tier_disclaimer(SafetyTier.TIER_4),
                override_response=self._tier4_block_message(),
                evidence_tags=[],
            )

        if self._contains_dangerous_a1c_target(query_lower, response_lower):
            return TierDecision(
                tier=SafetyTier.TIER_4,
                action=TierAction.BLOCK,
                reason="Unsafe A1C target detected; overly aggressive targets can increase hypoglycemia risk.",
                disclaimer=self._tier_disclaimer(SafetyTier.TIER_4),
                override_response=self._tier4_block_message(),
                evidence_tags=[],
            )

        # Tier 3: clinical decisions require provider input
        # Skip this check for educational strategy queries
        if not is_educational_query and self._is_clinical_decision(query_lower, response_lower):
            return TierDecision(
                tier=SafetyTier.TIER_3,
                action=TierAction.DEFER,
                reason="Clinical decision requires individualized assessment and clinician oversight.",
                disclaimer=self._tier_disclaimer(SafetyTier.TIER_3),
                override_response=self._tier3_defer_message(),
                evidence_tags=[],
            )

        # Tier 2: personalized analysis with small adjustments and testing
        if self._is_personalized_analysis(response_lower, sources_used, glooko_available):
            if self._has_small_adjustment(response_text) and self._has_testing_protocol(response_lower):
                return TierDecision(
                    tier=SafetyTier.TIER_2,
                    action=TierAction.ALLOW,
                    reason="Personalized pattern analysis with small, testable adjustments.",
                    disclaimer=self._tier_disclaimer(SafetyTier.TIER_2),
                    evidence_tags=self._evidence_tags(response_text, sources_used, rag_quality),
                )

        # Tier 1: evidence-based education (default)
        return TierDecision(
            tier=SafetyTier.TIER_1,
            action=TierAction.ALLOW,
            reason="Educational guidance with evidence markers or general self-management support.",
            disclaimer=self._tier_disclaimer(SafetyTier.TIER_1),
            evidence_tags=self._evidence_tags(response_text, sources_used, rag_quality),
        )

    def _contains_dangerous_advice(self, query_lower: str, response_lower: str) -> bool:
        return any(re.search(pattern, response_lower, re.IGNORECASE) for pattern in self.DANGEROUS_PATTERNS)

    def _is_educational_strategy_query(self, query_lower: str) -> bool:
        """
        Check if query is asking for educational strategies/advice (should be ALLOWED).
        
        Uses regex patterns first, falls back to LLM classification for ambiguous cases.
        """
        # Fast path: regex patterns
        if any(re.search(pattern, query_lower, re.IGNORECASE) for pattern in self.EDUCATIONAL_STRATEGY_PATTERNS):
            return True
        
        # Fallback: LLM-based intent classification for typos, grammar errors, semantic variations
        if self._llm_provider:
            return self._llm_classify_educational_intent(query_lower)
        
        return False

    def _llm_classify_educational_intent(self, query: str) -> bool:
        """
        Use LLM to classify if query is seeking educational guidance.
        
        Handles typos, grammar errors, and semantic variations that regex can't catch.
        """
        try:
            classification_prompt = f"""Classify this diabetes-related query.

A query is EDUCATIONAL if it asks:
- For strategies, tips, approaches, or general guidance on managing a situation
- How to handle, manage, improve, mitigate, deal with, or address a problem
- To explain concepts, patterns, or general diabetes management
- About ways to prevent or reduce problems
Examples: "how mitigate highs", "ways 2 handle low sugar", "tips for managing my glucose"

A query is PRESCRIPTIVE if it asks:
- For a specific insulin dose amount or calculation
- To determine exact medication doses or changes
- Clinical decisions like starting/stopping medications
Examples: "how much insulin for 200 mg/dl", "calculate my bolus", "should I stop my metformin"

Query: "{query}"

Think: Does this ask for general strategies/guidance (EDUCATIONAL) or specific doses/decisions (PRESCRIPTIVE)?
Answer with exactly one word: EDUCATIONAL or PRESCRIPTIVE"""

            # Quick synchronous LLM call (should be fast, ~100ms)
            from .llm_provider import GenerationConfig
            config = GenerationConfig(max_tokens=20, temperature=0.0)
            response = self._llm_provider.generate_text(classification_prompt, config=config)
            result = response.strip().upper()
            
            is_educational = "EDUCATIONAL" in result
            logger.info(f"LLM intent classification for '{query[:50]}...': {result} -> {'EDUCATIONAL' if is_educational else 'PRESCRIPTIVE'}")
            return is_educational
            
        except Exception as e:
            logger.warning(f"LLM intent classification failed: {e}, defaulting to regex-only")
            return False

    def _is_dosing_request(self, query_lower: str) -> bool:
        """Check if query is explicitly asking for a dose calculation (should be BLOCKED)."""
        return any(
            re.search(pattern, query_lower, re.IGNORECASE)
            for pattern in self.DOSING_REQUEST_PATTERNS
        )

    def _contains_specific_units(self, response_text: str) -> bool:
        return bool(self.UNITS_PATTERN.search(response_text or ""))

    def _contains_dangerous_a1c_target(self, query_lower: str, response_lower: str) -> bool:
        text = f"{query_lower} {response_lower}"
        for match in self.A1C_PATTERN.finditer(text):
            try:
                value = float(match.group(2))
            except (TypeError, ValueError):
                continue
            if value < 5.5:
                return True
        return False

    def _is_clinical_decision(self, query_lower: str, response_lower: str) -> bool:
        text = f"{query_lower} {response_lower}"
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in self.CLINICAL_DECISION_PATTERNS)

    def _is_personalized_analysis(
        self,
        response_lower: str,
        sources_used: list[str],
        glooko_available: bool,
    ) -> bool:
        if glooko_available or "glooko" in sources_used:
            return True
        return any(re.search(pattern, response_lower, re.IGNORECASE) for pattern in self.PERSONAL_DATA_MARKERS)

    def _has_small_adjustment(self, response_text: str) -> bool:
        for match in self.PERCENT_PATTERN.finditer(response_text or ""):
            try:
                value = int(match.group(1))
            except ValueError:
                continue
            if 0 < value <= 20:
                return True
        return False

    def _has_testing_protocol(self, response_lower: str) -> bool:
        return any(re.search(pattern, response_lower, re.IGNORECASE) for pattern in self.TESTING_MARKERS)

    def _evidence_tags(
        self,
        response_text: str,
        sources_used: list[str],
        rag_quality: dict,
    ) -> list[str]:
        tags = set()
        if "rag" in sources_used or rag_quality.get("chunk_count", 0) > 0:
            tags.add("rag")
        for pattern in self.EVIDENCE_MARKERS:
            if re.search(pattern, response_text or "", re.IGNORECASE):
                tags.add("named_guideline")
        return sorted(tags)

    def _tier_disclaimer(self, tier: SafetyTier) -> str:
        if tier == SafetyTier.TIER_1:
            return (
                "Disclaimer: Educational guidance based on published standards or manuals. "
                "Confirm any changes with your healthcare team."
            )
        if tier == SafetyTier.TIER_2:
            return (
                "Disclaimer: Personalized pattern analysis. Any changes should be small (≤20%) "
                "and tested with close monitoring and your care team."
            )
        if tier == SafetyTier.TIER_3:
            return (
                "Disclaimer: This is a clinical decision that requires your clinician’s oversight "
                "because it depends on your history, medications, and risk factors."
            )
        return (
            "Disclaimer: I can’t provide that because it could be unsafe. If you feel unwell or "
            "at risk, seek urgent medical care."
        )

    def _tier3_defer_message(self) -> str:
        return (
            "This decision depends on your medical history, current medications, and risk of hypoglycemia, "
            "so it should be made with your clinician. I can explain general principles, but I can’t guide "
            "a medication change without your care team."
        )

    def _tier4_block_message(self) -> str:
        return (
            "I can't help with that because it could be unsafe. If you're worried about your glucose or "
            "medications, please contact your healthcare team. If you feel acutely unwell, seek urgent care."
        )

    def _dosing_defer_message(self) -> str:
        return (
            "I can't calculate specific insulin doses because dosing depends on your individual factors "
            "(insulin sensitivity, carb ratios, activity level, and current glucose). Your healthcare team "
            "or diabetes educator can help you determine the right doses for your situation.\n\n"
            "I can help you understand general concepts like insulin-to-carb ratios, correction factors, "
            "or what questions to ask your care team about dosing."
        )
