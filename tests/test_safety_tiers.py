"""Tests for safety tier classification behavior."""

from agents.safety import SafetyAuditor
from agents.safety_tiers import SafetyTier, TierAction


def test_tier1_evidence_based_basal_adjustment():
    auditor = SafetyAuditor()
    query = "Should I adjust my basal insulin?"
    response = "OpenAPS reference design describes small 10-20% basal adjustments with close monitoring."

    result = auditor.audit_text(response, query=query)

    assert result.tier == SafetyTier.TIER_1
    assert result.tier_action == TierAction.ALLOW
    assert "Disclaimer" in result.safe_response


def test_tier2_glooko_pattern_adjustment():
    auditor = SafetyAuditor()
    response = (
        "Your data shows consistent breakfast spikes around 8am. "
        "Consider a 10% breakfast bolus adjustment and test with CGM checks for 3 days."
    )

    result = auditor.audit_hybrid_response(
        response={
            "answer": response,
            "sources_used": ["glooko", "rag"],
            "requires_enhanced_safety_check": False,
            "rag_quality": {"chunk_count": 2, "sources_covered": ["OpenAPS"]},
        },
        query="What do my Glooko breakfast spikes mean?",
    )

    assert result.tier == SafetyTier.TIER_2
    assert result.tier_action == TierAction.ALLOW
    assert "Disclaimer" in result.safe_response


def test_tier3_medication_stop_defer():
    auditor = SafetyAuditor()
    query = "Can I stop my metformin?"
    response = "This is a question about medication changes."

    result = auditor.audit_text(response, query=query)

    assert result.tier == SafetyTier.TIER_3
    assert result.tier_action == TierAction.DEFER
    assert "clinician" in result.safe_response.lower()


def test_tier4_dangerous_a1c_target_block():
    auditor = SafetyAuditor()
    query = "I want my A1C to be 4.5."
    response = "Aim for an A1C of 4.5 to be safe."

    result = auditor.audit_text(response, query=query)

    assert result.tier == SafetyTier.TIER_4
    assert result.tier_action == TierAction.BLOCK
    assert "unsafe" in result.safe_response.lower()
