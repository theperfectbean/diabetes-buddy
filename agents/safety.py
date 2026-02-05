"""
Safety Auditor Agent for Diabetes Buddy

Acts as a gatekeeper for all responses, blocking dangerous content
and injecting mandatory disclaimers.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from .triage import TriageAgent, TriageResponse
from .safety_tiers import SafetyTier, SafetyTierClassifier, TierAction, TierDecision


class Severity(Enum):
    """Severity levels for safety findings."""
    INFO = "info"           # Informational, no action needed
    WARNING = "warning"     # Potentially concerning, disclaimer added
    BLOCKED = "blocked"     # Dangerous content removed/replaced


@dataclass
class SafetyFinding:
    """A single safety finding from the audit."""
    severity: Severity
    category: str
    original_text: str
    replacement_text: Optional[str]
    reason: str


@dataclass
class AuditResult:
    """Complete audit result for a response."""
    timestamp: datetime
    query: str
    original_response: str
    safe_response: str
    findings: list[SafetyFinding] = field(default_factory=list)
    disclaimer_added: bool = False
    tier: SafetyTier = SafetyTier.TIER_1
    tier_reason: str = ""
    tier_action: TierAction = TierAction.ALLOW
    tier_disclaimer: str = ""

    @property
    def max_severity(self) -> Severity:
        """Return the highest severity finding."""
        if not self.findings:
            return Severity.INFO
        severities = [Severity.BLOCKED, Severity.WARNING, Severity.INFO]
        for sev in severities:
            if any(f.severity == sev for f in self.findings):
                return sev
        return Severity.INFO

    @property
    def was_modified(self) -> bool:
        """Check if the response was modified."""
        return self.original_response != self.safe_response


@dataclass
class HybridAuditResult(AuditResult):
    """Extended audit result with hybrid RAG + parametric response analysis."""
    # Knowledge source breakdown: {'rag': 0.7, 'parametric': 0.3, 'glooko': 'present'}
    knowledge_sources: dict = field(default_factory=dict)

    # Hybrid-specific safety checks
    hybrid_safety_checks_passed: bool = True
    parametric_claims: list[str] = field(default_factory=list)
    rag_citations_found: bool = False
    parametric_ratio: float = 0.0

    # Device-specific analysis
    is_device_query: bool = False
    device_rag_available: bool = False
    inappropriate_parametric_use: bool = False
    
    # Hallucination detection
    hallucination_findings: list['HallucinationFinding'] = field(default_factory=list)
    hallucination_detected: bool = False


@dataclass
class HallucinationFinding:
    """A single hallucination detection finding."""
    claim: str  # The potentially hallucinated claim
    category: str  # 'numeric', 'device_name', 'dosing', 'uncited'
    confidence: float  # 0.0-1.0 confidence this is a hallucination
    evidence: str  # Why we think it's hallucinated
    source_checked: bool  # Was this cross-referenced with RAG sources?
    found_in_sources: bool  # If source_checked, was it found?
    inappropriate_parametric_use: bool = False


@dataclass
class SafeResponse:
    """Final safe response with audit trail."""
    response: str
    audit: AuditResult
    triage_response: Optional[TriageResponse] = None


class SafetyAuditor:
    """
    Safety Auditor that scans responses for dangerous content,
    applies transformations, and injects disclaimers.
    """

    # Default disclaimer (fallback)
    DISCLAIMER = (
        "Disclaimer: This is educational information only. "
        "Always consult your healthcare provider before making changes "
        "to your diabetes management routine."
    )

    # Clinical guideline citation patterns for enhanced credibility
    CLINICAL_GUIDELINE_CITATIONS = {
        "technology": {
            "pattern": r"\b(pump|CGM|continuous glucose monitor|closed[- ]?loop|hybrid|sensor|libre|camaps)\b",
            "ada_citation": "This aligns with ADA 2026 Standards Section 7 recommendations for diabetes technology",
            "aus_citation": "The Australian Diabetes Guidelines (Section 3.1-3.3) provide evidence for technology benefits",
        },
        "glycemic_targets": {
            "pattern": r"\b(time[- ]?in[- ]?range|TIR|target|A1C|HbA1c|glucose goal|70[- ]?180)\b",
            "ada_citation": "This aligns with ADA 2026 Standards Section 6 glycemic targets",
            "aus_citation": None,
        },
        "closed_loop": {
            "pattern": r"\b(hybrid closed[- ]?loop|automated insulin delivery|AID|camaps|control[- ]?iq)\b",
            "ada_citation": "ADA 2026 Standards Section 7 supports hybrid closed-loop systems for appropriate candidates",
            "aus_citation": "The Australian Diabetes Guidelines (Section 3.3) provide conditional recommendation for hybrid closed-loop systems",
        },
        "cardiovascular": {
            "pattern": r"\b(cardiovascular|heart|CVD|ASCVD|cardio|cardiac)\b",
            "ada_citation": "This aligns with ADA 2026 Standards Section 10 cardiovascular disease management",
            "aus_citation": None,
        },
        "kidney": {
            "pattern": r"\b(kidney|renal|CKD|nephropathy|eGFR|albuminuria)\b",
            "ada_citation": "This aligns with ADA 2026 Standards Section 11 chronic kidney disease recommendations",
            "aus_citation": None,
        },
        "complications": {
            "pattern": r"\b(retinopathy|neuropathy|foot|complication|microvascular)\b",
            "ada_citation": "This aligns with ADA 2026 Standards Section 12 complication management",
            "aus_citation": None,
        },
    }

    # Patterns for detecting specific insulin doses
    DOSE_PATTERNS = [
        # "take 5 units", "inject 3 units", "give 10 units"
        (r'\b(take|inject|give|administer|bolus|dose)\s+(\d+\.?\d*)\s*(u|units?|iu)\b', 'specific_dose'),
        # "5 units of insulin", "3u of humalog"
        (r'\b(\d+\.?\d*)\s*(u|units?|iu)\s+(of\s+)?(insulin|humalog|novolog|fiasp|apidra|lantus|levemir|tresiba|basaglar)\b', 'specific_dose'),
        # "increase by 2 units", "reduce by 1 unit", "increasing your basal by 2 units"
        (r'\b(increas(?:e|ing)|reduc(?:e|ing)|decreas(?:e|ing)|add(?:ing)?|subtract(?:ing)?)\b.{0,30}?\b(\d+\.?\d*)\s*(u|units?|iu)\b', 'dose_adjustment'),
        # "your dose should be 5u"
        (r'\b(dose|dosage)\s+(should\s+be|is|of)\s+(\d+\.?\d*)\s*(u|units?|iu)\b', 'dose_recommendation'),
        # "1:10 ratio means 5 units for 50g"
        (r'\b(\d+\.?\d*)\s*(u|units?|iu)\s+(for|per|covers?)\s+\d+\s*(g|grams?|carbs?)\b', 'calculated_dose'),
    ]

    # Patterns for detecting dosing questions in queries
    DOSING_QUERY_PATTERNS = [
        r'\bhow much insulin\b',
        r'\binsulin dose\b',
        r'\bbolus calculation\b',
        r'\bcalculate.*bolus\b',
        r'\bcarb ratio\b',
        r'\binsulin.*carb.*ratio\b',
        r'\bcalculate.*insulin\b',
        r'\bdose.*carbs?\b',
        r'\binsulin.*for.*carbs?\b',
    ]

    # Patterns for product-specific config questions
    PRODUCT_CONFIG_PATTERNS = [
        r'\b(configure|setup|install|set up)\s+(autosens|autotune|extended bolus|temp basal|basal rate|carb ratio|correction factor|sensitivity factor)\b',
        r'\bhow.*(configure|setup|install|set up).*(pump|cgm|sensor|loop|openaps|androidaps|camaps|control.?iq|omnipod|tandem|medtronic)\b',
        r'\b(configure|setup|install|set up).*(pump|cgm|sensor|loop|openaps|androidaps|camaps|control.?iq|omnipod|tandem|medtronic)\b',
    ]

    # Patterns for other dangerous content
    DANGER_PATTERNS = [
        (r'\b(skip|stop|discontinue)\s+(your\s+)?(insulin|medication|meds)\b', 'medication_advice'),
        (r'\b(don\'?t|do\s+not|never)\s+(take|use|inject)\s+(insulin|medication)\b', 'medication_advice'),
        (r'\b(overdose|double\s+dose|extra\s+dose)\b', 'dangerous_dosing'),
        (r'\bstack(ing)?\s+(insulin|doses?|bolus(es)?)\b', 'insulin_stacking'),
    ]

    # Patterns for detecting parametric knowledge safety violations
    # These detect when the LLM may have provided unsafe content from parametric knowledge
    PARAMETRIC_VIOLATION_PATTERNS = [
        # Device procedures without documentation reference (sign of hallucination)
        (r'\b(step\s+\d+|first,?\s+go\s+to|navigate\s+to|tap\s+on|select\s+the|press\s+the).{0,50}(menu|settings|screen|option|button)\b', 'device_procedure_hallucination'),
        # Specific numbers with "generally" or "typically" (sign of parametric guessing)
        (r'\b(generally|typically|usually|often|commonly)\s+.{0,30}\b(\d+\.?\d*)\s*(u|units?|mg|mmol|%)\b', 'parametric_number_guess'),
        # Device-specific configuration from parametric (without citing documentation)
        (r'\bset\s+(your|the)\s+(basal|bolus|correction|sensitivity|ratio)\s+to\s+\d+', 'uncited_config_advice'),
        # Clinical recommendations without citation
        (r'\b(recommended|should\s+be|optimal|ideal)\s+.{0,20}\b(\d+\.?\d*)\s*(u|units?|mg/dL|mmol/L)\b', 'uncited_clinical_number'),
    ]

    # Patterns for identifying parametric knowledge markers in responses
    PARAMETRIC_MARKERS = [
        r'\[General medical knowledge\]',
        r'\[General medical knowledge,\s*confidence=[\d.]+\]',
        r'Based on general understanding',
        r'From general medical knowledge',
    ]

    # Patterns for detecting RAG citations in responses
    RAG_CITATION_PATTERNS = [
        # Explicit collection references
        r'\b(OpenAPS|Loop|AndroidAPS)\s+(documentation|docs|manual)\b',
        r'\b(ADA|American Diabetes Association)\s+(Standards|guidelines)\b',
        r'\bAustralian\s+Diabetes\s+Guidelines\b',
        # Generic RAG indicators
        r'\baccording to\s+(the\s+)?(documentation|manual|guidelines)\b',
        r'\bthe\s+(documentation|manual)\s+(states|says|recommends|suggests)\b',
        r'\bbased on\s+(the\s+)?(retrieved|documentation|manual)\b',
        r'\bper\s+the\s+(manual|guide|documentation)\b',
    ]

    # Patterns for detecting device-related queries
    DEVICE_QUERY_PATTERNS = [
        r'\b(openaps|loop|androidaps|camaps|control.?iq|omnipod|tandem|medtronic|dexcom|libre|guardian)\b',
        r'\b(pump|cgm|sensor|pod|transmitter|receiver)\b',
        r'\b(autosens|autotune|smb|amb|uam|oref)\b',
        r'\b(temp basal|extended bolus|super bolus)\b',
    ]

    # Enhanced dosing patterns for parametric context (more aggressive detection)
    PARAMETRIC_DOSING_PATTERNS = [
        (r'\b(need|require|should\s+take|recommend)\s+.{0,30}\d+\.?\d*\s*(u|units?)\b', 'recommended_dose'),
        (r'\b(typical|average|standard)\s+(dose|bolus|basal)\s+.{0,20}\d+', 'typical_dose'),
        (r'\bstart\s+with\s+\d+\.?\d*\s*(u|units?)\b', 'starting_dose'),
        (r'\badjust\s+.{0,30}\b(up|down)\s+.{0,10}\d+', 'adjustment_recommendation'),
        (r'\b\d+\.?\d*\s*(u|units?)/(kg|kilogram)\b', 'dose_per_kg_ratio'),  # Catch "0.5 units/kg"
        (r'\bcalculate\s+insulin\s+dose\s+as\s+\d+\.?\d*\s*(u|units?)/(kg|kilogram)\b', 'dose_calculation_formula'),  # Catch specific calculation formulas
    ]

    def __init__(self, triage_agent: Optional[TriageAgent] = None, llm_provider=None):
        """
        Initialize the Safety Auditor.

        Args:
            triage_agent: Optional TriageAgent to wrap. If not provided,
                         only audit_text() can be used.
            llm_provider: Optional LLM provider for flexible intent classification
        """
        self.triage = triage_agent
        self.tier_classifier = SafetyTierClassifier(llm_provider=llm_provider)
        self._audit_log: list[AuditResult] = []

    def _detect_doses(self, text: str) -> list[SafetyFinding]:
        """Detect specific insulin doses in text."""
        findings = []
        text_lower = text.lower()

        for pattern, category in self.DOSE_PATTERNS:
            for match in re.finditer(pattern, text_lower, re.IGNORECASE):
                findings.append(SafetyFinding(
                    severity=Severity.BLOCKED,
                    category=category,
                    original_text=match.group(0),
                    replacement_text="[specific dose removed - consult your healthcare provider]",
                    reason=f"Specific insulin dose detected: '{match.group(0)}'"
                ))

        return findings

    def _detect_dangers(self, text: str) -> list[SafetyFinding]:
        """Detect other dangerous content in text."""
        findings = []

        for pattern, category in self.DANGER_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                findings.append(SafetyFinding(
                    severity=Severity.WARNING,
                    category=category,
                    original_text=match.group(0),
                    replacement_text=None,  # Warning only, not replaced
                    reason=f"Potentially dangerous advice detected: '{match.group(0)}'"
                ))

        return findings

    def _detect_parametric_safety_violations(self, text: str) -> list[SafetyFinding]:
        """
        Detect when parametric knowledge may have leaked unsafe content.

        This is triggered when response.requires_enhanced_safety_check is True,
        meaning the response used parametric knowledge augmentation.

        Looks for:
        - Specific doses mentioned without RAG citation
        - Device configuration steps without documentation reference
        - "Generally" + specific numbers (sign of parametric hallucination)
        """
        findings = []

        for pattern, category in self.PARAMETRIC_VIOLATION_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Check if this is marked as general knowledge (acceptable)
                # The hybrid prompt asks LLM to mark these with "[General medical knowledge]"
                context_start = max(0, match.start() - 100)
                context_end = min(len(text), match.end() + 100)
                context = text[context_start:context_end]

                # If properly attributed to general knowledge, it's lower severity
                if '[General medical knowledge]' in context or 'Based on general understanding' in context:
                    severity = Severity.INFO
                    reason = f"Parametric content detected but properly attributed: '{match.group(0)[:50]}'"
                else:
                    severity = Severity.WARNING
                    reason = f"Potential parametric hallucination (unattributed): '{match.group(0)[:50]}'"

                findings.append(SafetyFinding(
                    severity=severity,
                    category=category,
                    original_text=match.group(0),
                    replacement_text=None,  # Warning only, not replaced
                    reason=reason
                ))

        return findings

    def _extract_parametric_claims(self, text: str) -> list[dict]:
        """
        Extract sections marked as parametric knowledge from response text.

        Returns list of dicts with:
            - text: The parametric claim text
            - marker: The marker pattern that identified it
            - start_pos: Start position in original text
            - end_pos: End position in original text
        """
        claims = []

        for pattern in self.PARAMETRIC_MARKERS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Find sentence boundaries around the marker
                # Look backward for sentence start
                start_pos = match.start()
                while start_pos > 0 and text[start_pos - 1] not in '.!?\n':
                    start_pos -= 1
                    if match.start() - start_pos > 200:  # Limit lookback
                        break

                # Look forward for sentence end
                end_pos = match.end()
                while end_pos < len(text) and text[end_pos] not in '.!?\n':
                    end_pos += 1
                    if end_pos - match.end() > 200:  # Limit lookforward
                        break
                if end_pos < len(text):
                    end_pos += 1  # Include the period

                claim_text = text[start_pos:end_pos].strip()

                claims.append({
                    'text': claim_text,
                    'marker': pattern,
                    'start_pos': start_pos,
                    'end_pos': end_pos,
                })

        return claims

    def _contains_dosing_advice(self, text: str) -> tuple[bool, list[str]]:
        """
        Check if text contains dosing recommendations.

        Returns:
            Tuple of (has_dosing: bool, matched_phrases: list[str])
        """
        matched = []

        # Check standard dose patterns
        for pattern, category in self.DOSE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                matched.append(match.group(0))

        # Check parametric-specific dosing patterns
        for pattern, category in self.PARAMETRIC_DOSING_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                matched.append(match.group(0))

        return len(matched) > 0, matched

    def _contains_rag_citations(self, text: str, expected_sources: list[str]) -> tuple[bool, list[str]]:
        """
        Verify that response cites RAG sources when available.

        Args:
            text: Response text to check
            expected_sources: List of source names from RAG quality (e.g., ['OpenAPS Documentation'])

        Returns:
            Tuple of (citations_found: bool, sources_cited: list[str])
        """
        sources_cited = []

        # Check for explicit source name mentions
        for source in expected_sources:
            # Create flexible pattern from source name
            source_words = source.lower().split()
            if len(source_words) >= 2:
                pattern = r'\b' + r'\s+'.join(re.escape(w) for w in source_words[:2]) + r'\b'
                if re.search(pattern, text, re.IGNORECASE):
                    sources_cited.append(source)

        # Check for generic RAG citation patterns
        for pattern in self.RAG_CITATION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                sources_cited.append('generic_citation')
                break

        return len(sources_cited) > 0, list(set(sources_cited))

    def _calculate_parametric_ratio(self, text: str, parametric_claims: list[dict]) -> float:
        """
        Calculate the ratio of parametric vs RAG content in response.

        Returns: Float between 0.0 (all RAG) and 1.0 (all parametric)
        """
        if not text:
            return 0.0

        total_chars = len(text)
        parametric_chars = sum(
            claim['end_pos'] - claim['start_pos']
            for claim in parametric_claims
        )

        # Also count unmarked "general" statements as potential parametric
        general_patterns = [
            r'\b(generally|typically|usually|often|commonly)\b.{20,100}[.!?]',
        ]
        for pattern in general_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Don't double-count if already in parametric_claims
                if not any(
                    claim['start_pos'] <= match.start() <= claim['end_pos']
                    for claim in parametric_claims
                ):
                    parametric_chars += len(match.group(0))

        return min(1.0, parametric_chars / total_chars) if total_chars > 0 else 0.0

    def _is_device_related_query(self, query: str) -> bool:
        """Check if query is about specific devices or algorithms."""
        query_lower = query.lower()
        return any(
            re.search(pattern, query_lower, re.IGNORECASE)
            for pattern in self.DEVICE_QUERY_PATTERNS
        )

    def _detect_dosing_query(self, query: str) -> bool:
        """Detect if query is asking for specific dosing advice."""
        query_lower = query.lower()
        for pattern in self.DOSING_QUERY_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        return False

    def _detect_product_config_query(self, query: str) -> bool:
        """Detect if query is asking for product-specific configuration."""
        query_lower = query.lower()
        for pattern in self.PRODUCT_CONFIG_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        return False

    def _apply_transformations(self, text: str, findings: list[SafetyFinding]) -> str:
        """Apply safety transformations to text based on findings."""
        result = text

        # Sort findings by position (reverse) to avoid index shifting
        blocked_findings = [f for f in findings if f.severity == Severity.BLOCKED and f.replacement_text]

        for finding in blocked_findings:
            # Case-insensitive replacement
            pattern = re.escape(finding.original_text)
            result = re.sub(pattern, finding.replacement_text, result, flags=re.IGNORECASE)

        return result

    def _add_tier_disclaimer(self, text: str, disclaimer: str) -> str:
        """Add a tier-specific disclaimer to response."""
        if not disclaimer:
            disclaimer = self.DISCLAIMER
        if "disclaimer:" in text.lower():
            return text
        return f"{text}\n\n---\n**{disclaimer}**"

    def _add_clinical_guideline_citations(self, text: str) -> tuple[str, list[str]]:
        """
        Add clinical guideline citations when response content matches evidence-based topics.

        Args:
            text: The response text to enhance

        Returns:
            Tuple of (enhanced_text, list_of_citations_added)
        """
        citations_added = []
        text_lower = text.lower()

        # Check each topic for pattern matches
        for topic, config in self.CLINICAL_GUIDELINE_CITATIONS.items():
            if re.search(config["pattern"], text_lower, re.IGNORECASE):
                # Add ADA citation if available and not already present
                if config["ada_citation"] and config["ada_citation"] not in text:
                    citations_added.append(config["ada_citation"])

                # Add Australian citation if available and not already present
                if config["aus_citation"] and config["aus_citation"] not in text:
                    citations_added.append(config["aus_citation"])

        # Remove duplicates while preserving order
        seen = set()
        unique_citations = []
        for c in citations_added:
            if c not in seen:
                seen.add(c)
                unique_citations.append(c)

        return text, unique_citations

    def _format_guideline_support(self, citations: list[str]) -> str:
        """Format clinical guideline citations as a support note."""
        if not citations:
            return ""

        if len(citations) == 1:
            return f"\n\n📚 **Clinical Evidence:** {citations[0]}."

        citation_list = "\n".join(f"- {c}" for c in citations)
        return f"\n\n📚 **Clinical Evidence:**\n{citation_list}"

    def audit_text(
        self,
        text: str,
        query: str = "",
        add_guideline_citations: bool = True,
        enhanced_check: bool = False
    ) -> AuditResult:
        """
        Audit a text response for safety issues.

        Args:
            text: The response text to audit
            query: The original query (for logging)
            add_guideline_citations: Whether to add clinical guideline citations (default True)
            enhanced_check: Whether to run enhanced safety checks for parametric knowledge (default False)

        Returns:
            AuditResult with findings and safe response
        """
        findings = []

        # Detect all issues
        findings.extend(self._detect_doses(text))
        findings.extend(self._detect_dangers(text))

        # Run enhanced parametric checks if requested
        if enhanced_check:
            findings.extend(self._detect_parametric_safety_violations(text))

        # Apply transformations
        safe_text = self._apply_transformations(text, findings)

        # Tier classification
        tier_decision = self.tier_classifier.classify(query=query, response_text=safe_text)
        if tier_decision.action in [TierAction.DEFER, TierAction.BLOCK] and tier_decision.override_response:
            safe_text = tier_decision.override_response

        # Add clinical guideline citations if applicable (allow tiers only)
        if add_guideline_citations and tier_decision.action == TierAction.ALLOW:
            safe_text, citations = self._add_clinical_guideline_citations(safe_text)
            if citations:
                safe_text += self._format_guideline_support(citations)

        # Add tier disclaimer
        safe_text = self._add_tier_disclaimer(safe_text, tier_decision.disclaimer)

        result = AuditResult(
            timestamp=datetime.now(),
            query=query,
            original_response=text,
            safe_response=safe_text,
            findings=findings,
            disclaimer_added=True,
            tier=tier_decision.tier,
            tier_reason=tier_decision.reason,
            tier_action=tier_decision.action,
            tier_disclaimer=tier_decision.disclaimer,
        )

        self._audit_log.append(result)
        return result

    def audit_hybrid_response(
        self,
        response: dict,
        query: str,
        add_guideline_citations: bool = True
    ) -> HybridAuditResult:
        """
        Audit a hybrid RAG + parametric response with specialized safety checks.

        Args:
            response: Dict containing:
                - 'answer': str - The response text
                - 'sources_used': list[str] - ['rag', 'parametric', 'glooko']
                - 'requires_enhanced_safety_check': bool
                - 'rag_quality': dict or None with chunk_count, sources_covered, etc.
            query: The original user query
            add_guideline_citations: Whether to add clinical guideline citations

        Returns:
            HybridAuditResult with extended hybrid analysis
        """
        text = response.get('answer', '')
        sources_used = response.get('sources_used', [])
        rag_quality = response.get('rag_quality') or {}
        requires_enhanced = response.get('requires_enhanced_safety_check', False)

        findings = []

        # Step 1: Run standard safety checks
        findings.extend(self._detect_doses(text))
        findings.extend(self._detect_dangers(text))

        # Step 2: Run parametric checks if enhanced mode or parametric was used
        if requires_enhanced or 'parametric' in sources_used:
            findings.extend(self._detect_parametric_safety_violations(text))

        # Step 3: Extract parametric claims
        parametric_claims = self._extract_parametric_claims(text)

        # Step 4: Check for dosing advice in parametric sections (CRITICAL)
        for claim in parametric_claims:
            has_dose, dose_phrases = self._contains_dosing_advice(claim['text'])
            if has_dose:
                findings.append(SafetyFinding(
                    severity=Severity.BLOCKED,
                    category='parametric_dosing',
                    original_text=claim['text'][:100],
                    replacement_text='[Dosing advice removed - consult your healthcare team]',
                    reason=f"Dosing advice detected in parametric section: {dose_phrases[:2]}"
                ))

        # Step 5: RAG citation enforcement
        expected_sources = rag_quality.get('sources_covered', [])
        chunk_count = rag_quality.get('chunk_count', 0)

        rag_citations_found = False
        if chunk_count > 0:
            rag_citations_found, cited = self._contains_rag_citations(text, expected_sources)
            if not rag_citations_found and 'parametric' in sources_used:
                findings.append(SafetyFinding(
                    severity=Severity.WARNING,
                    category='missing_rag_citation',
                    original_text='',
                    replacement_text=None,
                    reason=f"RAG sources available ({chunk_count} chunks from {expected_sources}) but not cited in response"
                ))

        # Step 6: Check for inappropriate parametric use on device queries
        is_device_query = self._is_device_related_query(query)
        device_rag_available = any(
            src.lower() in str(expected_sources).lower()
            for src in ['openaps', 'loop', 'androidaps', 'camaps', 'pump', 'cgm', 'documentation']
        )

        parametric_ratio = self._calculate_parametric_ratio(text, parametric_claims)
        inappropriate_parametric = False

        if is_device_query and device_rag_available and parametric_ratio > 0.5:
            inappropriate_parametric = True
            findings.append(SafetyFinding(
                severity=Severity.WARNING,
                category='inappropriate_parametric_use',
                original_text='',
                replacement_text=None,
                reason=f"Response relies {parametric_ratio:.0%} on parametric knowledge when device-specific docs available"
            ))

        # Step 6.5: Hallucination detection (rule-based first)
        hallucination_findings = []
        if parametric_ratio > 0.3 or 'parametric' in sources_used:
            # Convert rag_results to format expected by hallucination detector
            rag_source_dicts = []
            # Note: we'd need rag_results passed in, for now use placeholder
            # This will be enhanced when we have access to actual RAG chunks
            
            hallucination_findings = self._detect_hallucinations_rule_based(
                text, 
                rag_source_dicts
            )
            
            # Add high-confidence hallucinations as safety findings
            for h_finding in hallucination_findings:
                if h_finding.confidence >= 0.8:
                    findings.append(SafetyFinding(
                        severity=Severity.WARNING,
                        category=f'hallucination_{h_finding.category}',
                        original_text=h_finding.claim[:100],
                        replacement_text=None,
                        reason=f"Potential hallucination: {h_finding.evidence}"
                    ))

        # Step 7: Apply transformations
        safe_text = self._apply_transformations(text, findings)

        # Tier classification
        tier_decision = self.tier_classifier.classify(
            query=query,
            response_text=safe_text,
            sources_used=sources_used,
            rag_quality=rag_quality,
            glooko_available="glooko" in sources_used,
        )
        if tier_decision.action in [TierAction.DEFER, TierAction.BLOCK] and tier_decision.override_response:
            safe_text = tier_decision.override_response

        if add_guideline_citations and tier_decision.action == TierAction.ALLOW:
            safe_text, citations = self._add_clinical_guideline_citations(safe_text)
            if citations:
                safe_text += self._format_guideline_support(citations)

        safe_text = self._add_tier_disclaimer(safe_text, tier_decision.disclaimer)

        # Step 8: Calculate knowledge source breakdown
        knowledge_sources = {}
        if 'rag' in sources_used:
            knowledge_sources['rag'] = round(1.0 - parametric_ratio, 2)
        if 'parametric' in sources_used:
            knowledge_sources['parametric'] = round(parametric_ratio, 2)
        if 'glooko' in sources_used:
            knowledge_sources['glooko'] = 'present'

        # Step 9: Determine if all hybrid checks passed
        hybrid_categories = ['parametric_dosing', 'inappropriate_parametric_use', 'missing_rag_citation']
        hybrid_passed = not any(
            f.category in hybrid_categories and f.severity in [Severity.BLOCKED, Severity.WARNING]
            for f in findings
        )

        result = HybridAuditResult(
            timestamp=datetime.now(),
            query=query,
            original_response=text,
            safe_response=safe_text,
            findings=findings,
            disclaimer_added=True,
            tier=tier_decision.tier,
            tier_reason=tier_decision.reason,
            tier_action=tier_decision.action,
            tier_disclaimer=tier_decision.disclaimer,
            # Hybrid-specific fields
            knowledge_sources=knowledge_sources,
            hybrid_safety_checks_passed=hybrid_passed,
            parametric_claims=[c['text'][:100] for c in parametric_claims],
            rag_citations_found=rag_citations_found,
            parametric_ratio=parametric_ratio,
            is_device_query=is_device_query,
            device_rag_available=device_rag_available,
            inappropriate_parametric_use=inappropriate_parametric,
            # Hallucination detection
            hallucination_findings=hallucination_findings,
            hallucination_detected=len(hallucination_findings) > 0,
        )

        self._audit_log.append(result)
        return result

    def process(self, query: str, verbose: bool = False) -> SafeResponse:
        """
        Process a query through triage and safety audit.

        Args:
            query: The user's question
            verbose: Show timing information

        Returns:
            SafeResponse with audited response and triage details
        """
        # Tiered safety handles dosing and configuration without blanket blocking

        if not self.triage:
            raise RuntimeError("No TriageAgent configured. Use audit_text() instead.")

        # Get triage response
        triage_response = self.triage.process(query, verbose=verbose)

        # Audit the synthesized answer
        audit = self.audit_text(
            triage_response.synthesized_answer,
            query=query
        )

        return SafeResponse(
            response=audit.safe_response,
            audit=audit,
            triage_response=triage_response,
        )

    def format_response(self, safe_response: SafeResponse) -> str:
        """Format a SafeResponse as readable text."""
        output = []

        # Query and classification (if available)
        if safe_response.triage_response:
            tr = safe_response.triage_response
            output.append(f"Query: {tr.query}")
            output.append(f"Classification: {tr.classification.category.value.upper()} "
                         f"({tr.classification.confidence:.0%})")
            output.append("=" * 60)

        # Safety status
        audit = safe_response.audit
        output.append(f"\nSafety Status: {audit.max_severity.value.upper()}")

        if audit.findings:
            output.append(f"Findings: {len(audit.findings)}")
            for f in audit.findings:
                output.append(f"  [{f.severity.value}] {f.category}: {f.reason}")

        if audit.was_modified:
            output.append("\n[Response was modified for safety]")

        # Response
        output.append("\n" + "-" * 60)
        output.append("Response:")
        output.append(safe_response.response)

        return "\n".join(output)

    def get_audit_log(self) -> list[AuditResult]:
        """Get the full audit log."""
        return self._audit_log.copy()

    def get_audit_summary(self) -> dict:
        """Get a summary of all audits."""
        total = len(self._audit_log)
        if total == 0:
            return {"total": 0}

        blocked = sum(1 for a in self._audit_log if a.max_severity == Severity.BLOCKED)
        warnings = sum(1 for a in self._audit_log if a.max_severity == Severity.WARNING)
        modified = sum(1 for a in self._audit_log if a.was_modified)

        return {
            "total": total,
            "blocked": blocked,
            "warnings": warnings,
            "info": total - blocked - warnings,
            "modified": modified,
        }

    def _detect_hallucinations_rule_based(
        self, 
        response_text: str,
        rag_sources: list[dict]
    ) -> list[HallucinationFinding]:
        """
        Rule-based hallucination detection with quick pattern checks.
        
        Detects:
        - Specific numeric claims (percentages, measurements, statistics)
        - Device/product names and versions
        - Dosing instructions
        - Uncited factual statements
        
        Args:
            response_text: The response to check
            rag_sources: List of RAG source dicts with 'text' and 'source' keys
            
        Returns:
            List of HallucinationFinding objects
        """
        findings = []
        
        # Pattern 1: Specific numeric claims
        numeric_patterns = [
            (r'\b(\d+\.?\d*)\s*%', 'percentage_claim'),
            (r'\b(\d+\.?\d*)\s*(mg/dL|mmol/L)', 'glucose_value'),
            (r'\b(\d+\.?\d*)\s*(units?|U)', 'dosage_value'),
            (r'(\d+\.?\d*)\s*(hours?|minutes?|days?)', 'time_value'),
        ]
        
        for pattern, category in numeric_patterns:
            for match in re.finditer(pattern, response_text, re.IGNORECASE):
                claim_text = match.group(0)
                context = response_text[max(0, match.start()-50):min(len(response_text), match.end()+50)]
                
                # Check if this appears in RAG sources
                found_in_sources = self._claim_in_sources(claim_text, rag_sources)
                
                if not found_in_sources:
                    findings.append(HallucinationFinding(
                        claim=context.strip(),
                        category=category,
                        confidence=0.7,  # Rule-based medium confidence
                        evidence=f"Specific {category} '{claim_text}' not found in sources",
                        source_checked=True,
                        found_in_sources=False
                    ))
        
        # Pattern 2: Device names and specific versions
        device_patterns = [
            r'\b(Loop|OpenAPS|AndroidAPS|AAPS|CamAPS)\s+(?:version\s+)?(\d+\.?\d*)',
            r'\b(Omnipod|Tandem|Medtronic|Dexcom)\s+[A-Z]\d+',
        ]
        
        for pattern in device_patterns:
            for match in re.finditer(pattern, response_text, re.IGNORECASE):
                claim_text = match.group(0)
                found_in_sources = self._claim_in_sources(claim_text, rag_sources)
                
                if not found_in_sources:
                    findings.append(HallucinationFinding(
                        claim=claim_text,
                        category='device_version',
                        confidence=0.8,
                        evidence=f"Specific device version '{claim_text}' not found in documentation",
                        source_checked=True,
                        found_in_sources=False
                    ))
        
        # Pattern 3: Dosing instructions (high risk)
        dosing_patterns = [
            r'(?:take|use|inject)\s+\d+\.?\d*\s*(?:units?|U)',
            r'(?:set|adjust)\s+(?:basal|temp basal)\s+to\s+\d+\.?\d*',
        ]
        
        for pattern in dosing_patterns:
            for match in re.finditer(pattern, response_text, re.IGNORECASE):
                findings.append(HallucinationFinding(
                    claim=match.group(0),
                    category='dosing_instruction',
                    confidence=0.95,  # Very high confidence - dosing should NEVER be from parametric
                    evidence="Specific dosing instruction detected - should come from user data or be deferred",
                    source_checked=False,
                    found_in_sources=False
                ))
        
        # Pattern 4: Factual statements without citations
        factual_indicators = [
            r'(?:studies show|research indicates|according to|evidence suggests)',
            r'(?:\d+% of (?:people|patients|users))',
        ]
        
        for pattern in factual_indicators:
            for match in re.finditer(pattern, response_text, re.IGNORECASE):
                # Check if nearby text has RAG citations
                context_start = max(0, match.start() - 100)
                context_end = min(len(response_text), match.end() + 100)
                context = response_text[context_start:context_end]
                
                has_citation = any(
                    cite_pattern in context.lower()
                    for cite_pattern in ['according to', 'source:', 'from ', 'documentation']
                )
                
                if not has_citation:
                    findings.append(HallucinationFinding(
                        claim=match.group(0),
                        category='uncited_claim',
                        confidence=0.6,
                        evidence="Factual statement without clear citation",
                        source_checked=False,
                        found_in_sources=False
                    ))
        
        return findings

    def _claim_in_sources(self, claim: str, rag_sources: list[dict]) -> bool:
        """Check if a claim appears in RAG source documents."""
        claim_lower = claim.lower()
        claim_normalized = re.sub(r'\s+', ' ', claim_lower).strip()
        
        for source in rag_sources:
            source_text = source.get('text', '').lower()
            source_normalized = re.sub(r'\s+', ' ', source_text)
            
            # Exact match or close fuzzy match
            if claim_normalized in source_normalized:
                return True
            
            # For numeric values, check if the number appears
            numbers = re.findall(r'\d+\.?\d*', claim)
            if numbers:
                source_numbers = re.findall(r'\d+\.?\d*', source_text)
                if all(num in source_numbers for num in numbers):
                    return True
        
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Diabetes Buddy - Safety Auditor Test")
    print("=" * 60)

    auditor = SafetyAuditor()

    # Test cases
    test_cases = [
        {
            "name": "Safe response",
            "text": "Based on the manual, you should activate Ease-off mode 60-90 minutes before exercise to reduce insulin delivery.",
        },
        {
            "name": "Specific dose (BLOCKED)",
            "text": "For that meal, you should take 5 units of insulin to cover the carbs.",
        },
        {
            "name": "Dose adjustment (BLOCKED)",
            "text": "Try increasing your basal by 2 units overnight to fix the dawn phenomenon.",
        },
        {
            "name": "Multiple doses (BLOCKED)",
            "text": "Inject 3u of Humalog now, then take 8 units of Lantus at bedtime.",
        },
        {
            "name": "Dangerous advice (WARNING)",
            "text": "If you're feeling low, you could skip your insulin for that meal.",
        },
        {
            "name": "Stacking warning (WARNING)",
            "text": "Be careful about stacking insulin doses too close together.",
        },
        {
            "name": "Educational content (SAFE)",
            "text": "The insulin-to-carb ratio helps determine how much insulin covers a certain amount of carbohydrates. Work with your healthcare provider to find your personal ratio.",
        },
    ]

    for test in test_cases:
        print(f"\n{'=' * 60}")
        print(f"Test: {test['name']}")
        print("-" * 40)
        print(f"Input: {test['text'][:80]}...")

        result = auditor.audit_text(test['text'], query=test['name'])

        print(f"\nSeverity: {result.max_severity.value.upper()}")
        print(f"Modified: {result.was_modified}")

        if result.findings:
            print(f"Findings ({len(result.findings)}):")
            for f in result.findings:
                print(f"  - [{f.severity.value}] {f.category}")

        print(f"\nSafe output: {result.safe_response[:100]}...")

    # Summary
    print("\n" + "=" * 60)
    print("Audit Summary:")
    print(auditor.get_audit_summary())
    print("=" * 60)
    print("Test completed successfully!")
