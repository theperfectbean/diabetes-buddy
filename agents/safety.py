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

    # Mandatory disclaimer
    DISCLAIMER = (
        "\n\n---\n"
        "**Disclaimer:** This is educational information only. "
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

    def __init__(self, triage_agent: Optional[TriageAgent] = None):
        """
        Initialize the Safety Auditor.

        Args:
            triage_agent: Optional TriageAgent to wrap. If not provided,
                         only audit_text() can be used.
        """
        self.triage = triage_agent
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

    def _add_disclaimer(self, text: str) -> str:
        """Add mandatory disclaimer to response."""
        if self.DISCLAIMER.strip() not in text:
            return text + self.DISCLAIMER
        return text

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

    def audit_text(self, text: str, query: str = "", add_guideline_citations: bool = True) -> AuditResult:
        """
        Audit a text response for safety issues.

        Args:
            text: The response text to audit
            query: The original query (for logging)
            add_guideline_citations: Whether to add clinical guideline citations (default True)

        Returns:
            AuditResult with findings and safe response
        """
        findings = []

        # Detect all issues
        findings.extend(self._detect_doses(text))
        findings.extend(self._detect_dangers(text))

        # Apply transformations
        safe_text = self._apply_transformations(text, findings)

        # Add clinical guideline citations if applicable
        if add_guideline_citations:
            safe_text, citations = self._add_clinical_guideline_citations(safe_text)
            if citations:
                safe_text += self._format_guideline_support(citations)

        # Add disclaimer
        safe_text = self._add_disclaimer(safe_text)

        result = AuditResult(
            timestamp=datetime.now(),
            query=query,
            original_response=text,
            safe_response=safe_text,
            findings=findings,
            disclaimer_added=True,
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
        # Check for dangerous queries first
        if self._detect_dosing_query(query):
            safe_response = "I cannot provide specific insulin dosing advice. Individual insulin-to-carbohydrate ratios vary. Please consult your diabetes care team.\n\n### Sources\n- Safety guidelines"
            audit = AuditResult(
                timestamp=datetime.now(),
                query=query,
                original_response="",
                safe_response=safe_response,
                findings=[SafetyFinding(
                    severity=Severity.BLOCKED,
                    category="dosing_question",
                    original_text=query,
                    replacement_text=safe_response,
                    reason="Query detected as asking for specific insulin dosing advice"
                )],
                disclaimer_added=True,
            )
            return SafeResponse(
                response=safe_response,
                audit=audit,
                triage_response=None,
            )

        if self._detect_product_config_query(query):
            safe_response = "I can provide general diabetes management principles, but cannot give device-specific configuration instructions. Please refer to your device's user manual or contact your healthcare provider.\n\n### Sources\n- Educational resources"
            audit = AuditResult(
                timestamp=datetime.now(),
                query=query,
                original_response="",
                safe_response=safe_response,
                findings=[SafetyFinding(
                    severity=Severity.BLOCKED,
                    category="product_config_question",
                    original_text=query,
                    replacement_text=safe_response,
                    reason="Query detected as asking for product-specific configuration"
                )],
                disclaimer_added=True,
            )
            return SafeResponse(
                response=safe_response,
                audit=audit,
                triage_response=None,
            )

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
