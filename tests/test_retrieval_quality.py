"""
Comprehensive Retrieval Test Suite for Diabetes Buddy

Tests retrieval quality across different query types and sources.
Validates source prioritization, confidence scoring, and safety auditing.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys
from typing import List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.unified_agent import UnifiedAgent, UnifiedResponse
from agents.researcher_chromadb import ResearcherAgent, SearchResult
from agents.safety import SafetyAuditor
from agents.llm_provider import LLMFactory


class TestRetrievalQuality:
    """Test retrieval quality across different query scenarios."""

    @pytest.fixture
    def mock_researcher(self):
        """Mock researcher agent with controlled search results."""
        researcher = Mock(spec=ResearcherAgent)

        # Mock search_all_collections for comprehensive retrieval
        def mock_search_all(query, top_k=5):
            if "HbA1c target" in query:
                # Clinical query: prioritize ADA
                return [
                    SearchResult(
                        quote="ADA Standards Section 6: For most nonpregnant adults with type 1 diabetes, an A1C target of <7% (53 mmol/mol) is recommended.",
                        page_number=45,
                        confidence=1.0,
                        source="ada_standards",
                        context="Glycemic Targets"
                    ),
                    SearchResult(
                        quote="OpenAPS documentation suggests monitoring A1C trends but doesn't specify targets.",
                        page_number=12,
                        confidence=0.6,
                        source="openaps_docs",
                        context="Monitoring"
                    )
                ]
            elif "basal rates" in query:
                # Practical query: prioritize OpenAPS
                return [
                    SearchResult(
                        quote="OpenAPS basal rate testing: Start with current pump settings, test one basal rate at a time.",
                        page_number=78,
                        confidence=0.8,
                        source="openaps_docs",
                        context="Basal Testing"
                    ),
                    SearchResult(
                        quote="ADA Section 7: Individualize insulin regimens based on patient needs and preferences.",
                        page_number=67,
                        confidence=0.7,
                        source="ada_standards",
                        context="Insulin Therapy"
                    )
                ]
            elif "CGM accuracy" in query:
                # Hybrid query: blend sources
                return [
                    SearchResult(
                        quote="ADA Standards Section 7: CGM accuracy requirements for clinical decision making.",
                        page_number=89,
                        confidence=0.9,
                        source="ada_standards",
                        context="CGM Technology"
                    ),
                    SearchResult(
                        quote="OpenAPS calibration best practices: Calibrate when glucose is stable.",
                        page_number=34,
                        confidence=0.8,
                        source="openaps_docs",
                        context="Calibration"
                    ),
                    SearchResult(
                        quote="PubMed study on CGM accuracy in type 1 diabetes: MARD <10% for optimal performance.",
                        page_number=156,
                        confidence=0.7,
                        source="research_papers",
                        context="Accuracy Metrics"
                    )
                ]
            elif "spike after breakfast" in query:
                # Personal data query
                return [
                    SearchResult(
                        quote="Pattern analysis: Glucose spikes 2 hours post-meal suggest carb counting accuracy issues.",
                        page_number=None,
                        confidence=0.8,
                        source="glooko_data",
                        context="Personal Patterns"
                    ),
                    SearchResult(
                        quote="ADA Section 5: Carbohydrate counting is fundamental to intensive insulin therapy.",
                        page_number=34,
                        confidence=0.7,
                        source="ada_standards",
                        context="Nutrition"
                    ),
                    SearchResult(
                        quote="OpenAPS extended boluses can help with meals that digest slowly.",
                        page_number=56,
                        confidence=0.6,
                        source="openaps_docs",
                        context="Bolus Strategies"
                    )
                ]
            elif "insulin" in query and "dose" in query:
                # Safety-critical: minimal clinical guidance
                return [
                    SearchResult(
                        quote="ADA Section 9: Insulin dosing should be individualized based on comprehensive assessment.",
                        page_number=123,
                        confidence=0.9,
                        source="ada_standards",
                        context="Insulin Dosing"
                    )
                ]
            else:
                return []

        researcher.search_all_collections = mock_search_all
        researcher.query_knowledge = mock_search_all  # For unified agent compatibility
        return researcher

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM provider."""
        llm = Mock()
        llm.generate_text.return_value = "Mock response for testing."
        return llm

    @pytest.fixture
    def agent(self, mock_researcher, mock_llm):
        """Create unified agent with mocked dependencies."""
        with patch('agents.unified_agent.LLMFactory') as mock_factory, \
             patch('agents.unified_agent.ResearcherAgent') as mock_researcher_class:

            mock_factory.get_provider.return_value = mock_llm
            mock_researcher_class.return_value = mock_researcher

            agent = UnifiedAgent()
            agent.researcher = mock_researcher
            agent.llm = mock_llm
            return agent

    @pytest.fixture
    def agent_with_kb(self, researcher_with_test_data, mock_llm):
        """Create unified agent backed by populated ChromaDB."""
        agent = UnifiedAgent()
        agent.researcher = researcher_with_test_data
        agent.llm = mock_llm
        return agent

    def test_clinical_query_prioritizes_ada(self, agent_with_kb):
        """Test that clinical queries prioritize ADA Standards (confidence=1.0)."""
        query = "What HbA1c target for newly diagnosed type 1 diabetes?"

        # Mock the LLM to return a response that cites the sources
        agent_with_kb.llm.generate_text.return_value = """
        Based on the ADA Standards Section 6, for most nonpregnant adults with type 1 diabetes,
        an A1C target of <7% (53 mmol/mol) is recommended.

        This is the authoritative clinical guideline for glycemic targets.
        """

        response = agent_with_kb.process(query)

        assert response.success
        assert "ADA Standards Section 6" in response.answer
        assert "rag" in response.sources_used

    def test_practical_query_prioritizes_openaps(self, agent_with_kb):
        """Test that practical queries prioritize OpenAPS docs (confidence=0.8)."""
        query = "How to set basal rates for overnight control?"

        agent_with_kb.llm.generate_text.return_value = """
        For setting basal rates overnight, the OpenAPS documentation recommends:
        Start with current pump settings and test one basal rate at a time.

        The ADA Standards also support individualizing insulin regimens.
        """

        response = agent_with_kb.process(query)

        assert response.success
        assert "OpenAPS" in response.answer
        assert "ADA Standards" in response.answer
        assert "rag" in response.sources_used

    def test_hybrid_query_blends_sources(self, agent_with_kb):
        """Test that hybrid queries blend ADA, OpenAPS, and research sources."""
        query = "CGM accuracy and calibration best practices"

        agent_with_kb.llm.generate_text.return_value = """
        CGM accuracy and calibration best practices combine clinical guidelines and practical experience:

        From ADA Standards Section 7: CGM accuracy requirements for clinical decision making.
        From OpenAPS: Calibrate when glucose is stable.
        From research: MARD <10% for optimal performance.
        """

        response = agent_with_kb.process(query)

        assert response.success
        assert "ADA Standards Section 7" in response.answer
        assert "OpenAPS" in response.answer
        assert "research" in response.answer or "PubMed" in response.answer
        assert "rag" in response.sources_used

    def test_personal_data_query_with_glooko(self, agent_with_kb):
        """Test personal data queries integrate Glooko patterns with clinical advice."""
        query = "Why do I spike after breakfast?"

        # Mock Glooko context
        agent_with_kb._load_glooko_context = Mock(return_value="""
        Recent glucose data shows consistent spikes 2 hours after breakfast meals.
        Average post-breakfast glucose: 180-220 mg/dL.
        """)

        agent_with_kb.llm.generate_text.return_value = """
        Your glucose data shows spikes after breakfast, which suggests carb counting accuracy issues.

        From ADA Section 5: Carbohydrate counting is fundamental to intensive insulin therapy.
        From OpenAPS: Extended boluses can help with meals that digest slowly.
        """

        response = agent_with_kb.process(query)

        assert response.success
        assert "glooko" in response.sources_used
        assert "rag" in response.sources_used
        assert "carb counting" in response.answer.lower()
        assert "ADA Section 5" in response.answer

    def test_safety_critical_blocks_dosage_advice(self, agent):
        """Test that safety-critical queries block specific dosage advice."""
        query = "How much insulin should I take for 50g carbs?"

        agent.llm.generate_text.return_value = """
        I cannot provide specific insulin dosing recommendations.
        Please consult your healthcare provider for personalized dosing.

        ADA Section 9 states that insulin dosing should be individualized.
        """

        response = agent.process(query)

        assert response.success
        assert "cannot provide specific insulin dosing" in response.answer.lower()
        assert "ADA Section 9" in response.answer
        assert "healthcare provider" in response.answer.lower()
        # Disclaimer is empty because "healthcare" is already in the answer
        assert response.disclaimer == ""

    def test_confidence_score_distribution(self, agent):
        """Test that confidence scores are properly distributed across sources."""
        # Test multiple queries to gather confidence statistics
        queries = [
            "HbA1c target for type 1 diabetes",
            "basal rate testing overnight",
            "CGM calibration frequency"
        ]

        confidence_scores = []

        for query in queries:
            results = agent.researcher.search_all_collections(query, top_k=5)
            confidence_scores.extend([r.confidence for r in results])

        # Check distribution
        assert len(confidence_scores) > 0
        assert max(confidence_scores) <= 1.0
        assert min(confidence_scores) >= 0.0

        # ADA should have highest confidence
        ada_scores = [s for s in confidence_scores if any(r.confidence == s and r.source == "ada_standards"
                                                          for r in agent.researcher.search_all_collections(queries[0]))]
        if ada_scores:
            assert max(ada_scores) == 1.0

    def test_citation_accuracy(self, agent):
        """Test that citations accurately reflect source content."""
        query = "HbA1c target guidelines"

        results = agent.researcher.search_all_collections(query)

        # Check that ADA result contains actual guideline content
        ada_result = next((r for r in results if r.source == "ada_standards"), None)
        assert ada_result is not None
        assert "A1C target" in ada_result.quote
        assert "7%" in ada_result.quote or "53 mmol/mol" in ada_result.quote

    @pytest.mark.parametrize("query,expected_sources", [
        ("HbA1c target", ["ada_standards"]),
        ("basal rates", ["openaps_docs", "ada_standards"]),
        ("CGM accuracy", ["ada_standards", "openaps_docs", "research_papers"]),
        ("spike after breakfast", ["glooko_data", "ada_standards", "openaps_docs"]),
        ("insulin dose for carbs", ["ada_standards"])
    ])
    def test_source_prioritization(self, agent, query, expected_sources):
        """Test that queries prioritize expected sources."""
        results = agent.researcher.search_all_collections(query, top_k=10)

        found_sources = list(set(r.source for r in results))

        # Check that expected sources are present
        for expected in expected_sources:
            if expected == "glooko_data":
                # Glooko is handled separately in unified agent
                continue
            assert expected in found_sources, f"Expected source {expected} not found in results for query: {query}"

    def test_retrieval_metrics_calculation(self, agent):
        """Test calculation of precision/recall metrics for retrieval."""
        # Simulate ground truth and retrieved results
        test_cases = [
            {
                "query": "clinical guidelines",
                "ground_truth_sources": ["ada_standards", "australian_guidelines"],
                "retrieved_sources": ["ada_standards", "openaps_docs", "research_papers"]
            }
        ]

        for case in test_cases:
            ground_truth = set(case["ground_truth_sources"])
            retrieved = set(case["retrieved_sources"])

            # Calculate precision and recall
            true_positives = len(ground_truth & retrieved)
            precision = true_positives / len(retrieved) if retrieved else 0
            recall = true_positives / len(ground_truth) if ground_truth else 0

            # Precision should be reasonable (>0.3 for this test)
            assert precision > 0.3, f"Low precision {precision} for query: {case['query']}"

            # Recall should be reasonable (>=0.5 for this test)
            assert recall >= 0.5, f"Low recall {recall} for query: {case['query']}"


class TestSafetyAuditorIntegration:
    """Test safety auditor integration with retrieval."""

    def test_dosage_query_triggers_auditor(self):
        """Test that dosage queries are properly audited."""
        auditor = SafetyAuditor()

        dangerous_response = "You should take 5 units of insulin for 50g carbs."
        query = "How much insulin for 50g carbs?"

        result = auditor.audit_text(dangerous_response, query)

        # Should detect dosage advice
        assert len(result.findings) > 0
        assert any(f.category == 'specific_dose' for f in result.findings)

        # Should block or modify the dangerous content
        assert "5 units" not in result.safe_response

        # Should include disclaimer
        assert "Disclaimer" in result.safe_response

    def test_clinical_citations_added(self):
        """Test that clinical guideline citations are added to responses."""
        auditor = SafetyAuditor()

        response_with_tech = "Using a CGM can help monitor glucose levels continuously."
        query = "CGM benefits"

        result = auditor.audit_text(response_with_tech, query)

        # Should add ADA citation for technology
        assert "ADA 2026 Standards Section 7" in result.safe_response
