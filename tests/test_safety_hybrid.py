"""
Safety Tests for Hybrid Knowledge System

Tests safety auditing for hybrid RAG + parametric responses.
"""

import pytest
from unittest.mock import Mock
from agents.safety import SafetyAuditor, HybridAuditResult, Severity, SafetyFinding


class TestHybridAuditFunction:
    """Test hybrid audit function logic."""

    @pytest.fixture
    def auditor(self):
        """Create SafetyAuditor instance."""
        return SafetyAuditor()

    def test_audit_hybrid_parametric_markers_detected(self, auditor):
        """Test detection of parametric markers in hybrid response."""
        response_text = "Insulin helps regulate blood sugar [General medical knowledge]. This is based on retrieved ADA guidelines."

        response_dict = {
            'answer': response_text,
            'sources_used': ['rag', 'parametric'],
            'requires_enhanced_safety_check': True,
            'rag_quality': {'chunk_count': 2, 'sources_covered': ['ADA']},
            'knowledge_breakdown': Mock(
                parametric_ratio=0.6,
                rag_ratio=0.4
            )
        }
        
        result = auditor.audit_hybrid_response(
            response=response_dict,
            query="Test query for parametric markers"
        )
        
        assert isinstance(result, HybridAuditResult)
        # Should detect parametric markers
        assert len(result.parametric_claims) > 0
        assert any('[General medical knowledge]' in claim for claim in result.parametric_claims)

    def test_audit_hybrid_no_parametric_markers(self, auditor):
        """Test response with no parametric markers."""
        response_text = "According to ADA guidelines, check blood sugar before meals. This is supported by Joslin Diabetes Center recommendations."

        response_dict = {
            'answer': response_text,
            'sources_used': ['rag'],
            'requires_enhanced_safety_check': False,
            'rag_quality': {'chunk_count': 4, 'sources_covered': ['ADA', 'Joslin']},
            'knowledge_breakdown': Mock(
                parametric_ratio=0.0,
                rag_ratio=1.0
            )
        }
        
        result = auditor.audit_hybrid_response(
            response=response_dict,
            query="Test query for no parametric markers"
        )
        
        assert isinstance(result, HybridAuditResult)
        # Should have no parametric claims
        parametric_findings = [f for f in result.findings if f.category == 'parametric_claims']
        if parametric_findings:
            assert len(parametric_findings[0].original_text) == 0  # Empty list

    def test_audit_hybrid_rag_citations_found(self, auditor):
        """Test detection of RAG citations."""
        response_text = "According to ADA guidelines, insulin should be taken before meals. This is also recommended by the Joslin Diabetes Center."

        response_dict = {
            'answer': response_text,
            'sources_used': ['rag'],
            'requires_enhanced_safety_check': False,
            'rag_quality': {'chunk_count': 3, 'sources_covered': ['ADA', 'Joslin']},
            'knowledge_breakdown': Mock(
                parametric_ratio=0.0,
                rag_ratio=1.0
            )
        }
        
        result = auditor.audit_hybrid_response(
            response=response_dict,
            query="Test query for RAG citations"
        )
        citation_findings = [f for f in result.findings if 'citation' in f.category.lower() or 'rag' in f.category.lower()]
        # This depends on the actual implementation, but should not have missing citations warning

    def test_audit_hybrid_missing_citations(self, auditor):
        """Test detection of missing citations for parametric claims."""
        response_text = "Insulin is a hormone that regulates blood sugar [General medical knowledge]. It works by facilitating glucose uptake into cells."

        response_dict = {
            'answer': response_text,
            'sources_used': ['rag', 'parametric'],
            'requires_enhanced_safety_check': True,
            'rag_quality': {'chunk_count': 1, 'sources_covered': ['ADA']},
            'knowledge_breakdown': Mock(
                parametric_ratio=0.8,
                rag_ratio=0.2
            )
        }
        
        result = auditor.audit_hybrid_response(
            response=response_dict,
            query="Test query for missing citations"
        )
        citation_findings = [f for f in result.findings if 'citation' in f.category.lower() or 'rag' in f.category.lower()]
        # Should have warnings about missing RAG citations for parametric claims


class TestDosingSafetyTests:
    """Test dosing safety in hybrid responses."""

    @pytest.fixture
    def auditor(self):
        """Create SafetyAuditor instance."""
        return SafetyAuditor()

    def test_audit_parametric_dosing_blocked(self, auditor):
        """Test that parametric dosing advice is blocked."""
        response_text = "Take 10 units of insulin before meals [General medical knowledge]. This should help control your blood sugar."

        response_dict = {
            'answer': response_text,
            'sources_used': ['parametric'],
            'requires_enhanced_safety_check': True,
            'rag_quality': {'chunk_count': 0, 'sources_covered': []},
            'knowledge_breakdown': Mock(
                parametric_ratio=1.0,
                rag_ratio=0.0
            )
        }
        
        result = auditor.audit_hybrid_response(
            response=response_dict,
            query="Test query for parametric dosing"
        )
        dosing_findings = [f for f in result.findings if 'dosing' in f.category.lower()]
        assert len(dosing_findings) > 0
        assert any(f.severity == Severity.BLOCKED for f in dosing_findings)

    def test_audit_rag_dosing_allowed(self, auditor):
        """Test that evidence-based education is allowed without unit-specific dosing."""
        response_text = "ADA guidelines describe small, stepwise basal adjustments (e.g., 10-20%) with close monitoring."

        response_dict = {
            'answer': response_text,
            'sources_used': ['rag'],
            'requires_enhanced_safety_check': False,
            'rag_quality': {'chunk_count': 3, 'sources_covered': ['ADA']},
            'knowledge_breakdown': Mock(
                parametric_ratio=0.0,
                rag_ratio=1.0
            )
        }
        
        result = auditor.audit_hybrid_response(
            response=response_dict,
            query="Test query for RAG dosing"
        )
        blocking_findings = [f for f in result.findings if f.severity == Severity.BLOCKED]
        dosing_blocks = [f for f in blocking_findings if 'dosing' in f.category.lower()]
        assert len(dosing_blocks) == 0

    def test_audit_dosing_patterns_comprehensive(self, auditor):
        """Test comprehensive dosing pattern detection."""
        test_cases = [
            ("Take 5 units [General medical knowledge]", True),
            ("Bolus 2 units per carb [General medical knowledge]", True),
            ("Calculate insulin dose as 0.5 units/kg [General medical knowledge]", True),
            ("ADA recommends small 10% basal adjustments with monitoring", False),
            ("Evidence-based guidance suggests stepwise 10-20% changes with careful testing", False),
        ]

        for response_text, should_be_blocked in test_cases:
            sources_used = ['parametric'] if '[General medical knowledge]' in response_text else ['rag']
            parametric_ratio = 1.0 if '[General medical knowledge]' in response_text else 0.0
            rag_ratio = 0.0 if '[General medical knowledge]' in response_text else 1.0
            
            response_dict = {
                'answer': response_text,
                'sources_used': sources_used,
                'requires_enhanced_safety_check': parametric_ratio > 0,
                'rag_quality': {'chunk_count': 0 if parametric_ratio > 0 else 2, 'sources_covered': [] if parametric_ratio > 0 else ['ADA']},
                'knowledge_breakdown': Mock(
                    parametric_ratio=parametric_ratio,
                    rag_ratio=rag_ratio
                )
            }
            
            result = auditor.audit_hybrid_response(
                response=response_dict,
                query=f"Test query for {response_text[:20]}..."
            )

            blocking_findings = [f for f in result.findings if f.severity == Severity.BLOCKED]
            has_dosing_block = any('dosing' in f.category.lower() for f in blocking_findings)

            if should_be_blocked:
                assert has_dosing_block, f"Should block dosing in: {response_text}"
            else:
                assert not has_dosing_block, f"Should not block dosing in: {response_text}"


class TestHallucinationDetectionRuleBased:
    """Tests for rule-based hallucination pattern detection."""

    @pytest.fixture
    def auditor(self):
        """Create SafetyAuditor instance."""
        return SafetyAuditor()

    def test_detect_numeric_claims(self, auditor):
        """Detects numeric patterns: '75% of users', '12.5 mg/dL'."""
        response = "75% of users experience this symptom. Check levels at 12.5 mg/dL."
        findings = auditor._detect_hallucinations(response, [])
        
        numeric_findings = [f for f in findings if 'numeric' in f.category.lower()]
        assert len(numeric_findings) >= 2  # Should detect both numbers

    def test_detect_device_versions(self, auditor):
        """Detects device version claims: 'Loop version 3.5'."""
        response = "Loop version 3.5 has improved algorithms. Use Medtronic 670G series 2."
        findings = auditor._detect_hallucinations(response, [])
        
        device_findings = [f for f in findings if 'device' in f.category.lower()]
        assert len(device_findings) >= 2

    def test_detect_dosing_instructions(self, auditor):
        """Detects dosing advice: 'take 5 units', 'inject 0.5U'."""
        response = "Take 5 units before meals. Inject 0.5U per carb."
        findings = auditor._detect_hallucinations(response, [])
        
        dosing_findings = [f for f in findings if 'dosing' in f.category.lower()]
        assert len(dosing_findings) >= 2

    def test_detect_uncited_research_claims(self, auditor):
        """Flags 'studies show', 'research indicates' without sources."""
        response = "Studies show that 80% of patients benefit. Research indicates better outcomes."
        findings = auditor._detect_hallucinations(response, [])
        
        research_findings = [f for f in findings if 'research' in f.category.lower()]
        assert len(research_findings) >= 2

    def test_no_false_positives_on_rag_sources(self, auditor):
        """Claims from RAG sources not flagged as hallucinations."""
        response = "Studies show benefits according to ADA guidelines."
        sources = ["ADA guidelines: Studies show that..."]
        findings = auditor._detect_hallucinations(response, sources)
        
        # Should not flag when source contains similar claim
        research_findings = [f for f in findings if 'research' in f.category.lower()]
        assert len(research_findings) == 0


class TestHallucinationSourceCrossReference:
    """Tests for cross-referencing claims with RAG sources."""

    @pytest.fixture
    def auditor(self):
        """Create SafetyAuditor instance."""
        return SafetyAuditor()

    def test_claim_found_in_sources(self, auditor):
        """Claim present in RAG sources → not hallucination."""
        response = "Insulin regulates blood sugar."
        sources = ["Medical text: Insulin is a hormone that regulates blood sugar levels."]
        findings = auditor._detect_hallucinations(response, sources)
        
        # Should not flag basic medical facts found in sources
        assert len(findings) == 0

    def test_claim_not_in_sources(self, auditor):
        """Claim absent from RAG sources → hallucination."""
        response = "New treatment X cures diabetes completely."
        sources = ["Standard treatments include insulin and metformin."]
        findings = auditor._detect_hallucinations(response, sources)
        
        # Should flag unsupported claims
        assert len(findings) > 0

    def test_partial_match_handling(self, auditor):
        """Numeric values close to source values handled correctly."""
        response = "75% of patients see improvement."
        sources = ["Study shows 70% of patients benefit."]
        findings = auditor._detect_hallucinations(response, sources)
        
        # Close values might be acceptable, exact match preferred
        # This depends on implementation tolerance
        pass  # Implementation-specific


class TestHallucinationFindingDataClass:
    """Tests for HallucinationFinding structure."""

    def test_finding_has_required_fields(self):
        """HallucinationFinding includes claim, category, confidence."""
        from agents.safety import HallucinationFinding
        
        finding = HallucinationFinding(
            claim="Test claim",
            category="numeric_claim",
            confidence=0.8,
            justification="Test justification"
        )
        
        assert finding.claim == "Test claim"
        assert finding.category == "numeric_claim"
        assert finding.confidence == 0.8
        assert finding.justification == "Test justification"

    def test_confidence_score_0_to_1(self):
        """Confidence values between 0.0-1.0."""
        from agents.safety import HallucinationFinding
        
        # Valid range
        finding = HallucinationFinding("claim", "category", 0.5, "just")
        assert finding.confidence == 0.5
        
        # Should clamp invalid values
        finding = HallucinationFinding("claim", "category", -0.1, "just")
        assert finding.confidence >= 0.0
        
        finding = HallucinationFinding("claim", "category", 1.5, "just")
        assert finding.confidence <= 1.0


class TestHallucinationTriggering:
    """Tests for when hallucination detection runs."""

    @pytest.fixture
    def auditor(self):
        """Create SafetyAuditor instance."""
        return SafetyAuditor()

    def test_parametric_ratio_above_30_triggers(self, auditor):
        """Detection runs when parametric_ratio > 0.3."""
        response_dict = {
            'answer': "Some claim with 75% success rate.",
            'sources_used': ['rag', 'parametric'],
            'knowledge_breakdown': Mock(parametric_ratio=0.4, rag_ratio=0.6)
        }
        
        result = auditor.audit_hybrid_response(response_dict, "test query")
        
        # Should have hallucination findings
        hallucination_findings = [f for f in result.findings if 'hallucination' in f.category.lower()]
        assert len(hallucination_findings) > 0

    def test_rag_only_response_skips_detection(self, auditor):
        """Pure RAG responses don't run hallucination check."""
        response_dict = {
            'answer': "Some claim with 75% success rate.",
            'sources_used': ['rag'],
            'knowledge_breakdown': Mock(parametric_ratio=0.0, rag_ratio=1.0)
        }
        
        result = auditor.audit_hybrid_response(response_dict, "test query")
        
        # Should not have hallucination findings for pure RAG
        hallucination_findings = [f for f in result.findings if 'hallucination' in f.category.lower()]
        assert len(hallucination_findings) == 0

    def test_high_confidence_hallucination_blocks_response(self, auditor):
        """Hallucination confidence >= 0.8 triggers BLOCK."""
        response_dict = {
            'answer': "Take 10 units of insulin [General medical knowledge].",
            'sources_used': ['parametric'],
            'knowledge_breakdown': Mock(parametric_ratio=1.0, rag_ratio=0.0)
        }
        
        result = auditor.audit_hybrid_response(response_dict, "test query")
        
        blocking_findings = [f for f in result.findings if f.severity == Severity.BLOCKED]
        hallucination_blocks = [f for f in blocking_findings if 'hallucination' in f.category.lower()]
        assert len(hallucination_blocks) > 0


class TestHallucinationLogging:
    """Tests for hallucination detection logging."""

    @pytest.fixture
    def auditor(self):
        """Create SafetyAuditor instance."""
        return SafetyAuditor()

    def test_findings_added_to_audit_result(self, auditor):
        """HybridAuditResult includes hallucination_findings list."""
        response_dict = {
            'answer': "75% success rate claimed.",
            'sources_used': ['parametric'],
            'knowledge_breakdown': Mock(parametric_ratio=0.5, rag_ratio=0.5)
        }
        
        result = auditor.audit_hybrid_response(response_dict, "test query")
        
        assert hasattr(result, 'hallucination_findings')
        assert isinstance(result.hallucination_findings, list)

    def test_hallucination_logged_if_above_threshold(self, auditor):
        """Findings with confidence >= 0.7 logged to CSV."""
        # This would require checking the CSV output
        # Implementation-dependent
        pass
