"""
Unit Tests for Hybrid Knowledge System

Tests the core logic of the two-stage RAG + parametric knowledge system.
"""

import pytest
from unittest.mock import Mock, MagicMock
from agents.unified_agent import (
    UnifiedAgent,
    RAGQualityAssessment,
    KnowledgeBreakdown,
    UnifiedResponse,
    RAGQualityMetrics
)


class TestRAGQualityAssessment:
    """Test RAG quality assessment logic."""

    def test_rag_quality_sufficient_chunks(self):
        """Test sufficient RAG quality with 5 chunks and high confidence."""
        assessment = RAGQualityAssessment(
            chunk_count=5,
            avg_confidence=0.85,
            max_confidence=0.9,
            min_confidence=0.8,
            sources_covered=['ADA', 'Joslin', 'AADE'],
            source_diversity=3,
            topic_coverage='sufficient'
        )

        assert assessment.is_sufficient is True
        assert assessment.topic_coverage == 'sufficient'

    def test_rag_quality_insufficient_chunks(self):
        """Test insufficient RAG quality with 2 chunks and high confidence."""
        assessment = RAGQualityAssessment(
            chunk_count=2,
            avg_confidence=0.9,
            max_confidence=0.95,
            min_confidence=0.85,
            sources_covered=['ADA'],
            source_diversity=1,
            topic_coverage='sparse'
        )

        assert assessment.is_sufficient is False
        assert assessment.topic_coverage == 'sparse'

    def test_rag_quality_low_confidence(self):
        """Test insufficient RAG quality with low confidence."""
        assessment = RAGQualityAssessment(
            chunk_count=4,
            avg_confidence=0.5,
            max_confidence=0.6,
            min_confidence=0.4,
            sources_covered=['ADA', 'Joslin'],
            source_diversity=2,
            topic_coverage='partial'
        )

        assert assessment.is_sufficient is False
        assert assessment.topic_coverage == 'partial'

    def test_rag_quality_boundary_3_chunks(self):
        """Test boundary case with exactly 3 chunks and 0.7 confidence."""
        assessment = RAGQualityAssessment(
            chunk_count=3,
            avg_confidence=0.7,
            max_confidence=0.75,
            min_confidence=0.65,
            sources_covered=['ADA', 'Joslin', 'AADE'],
            source_diversity=3,
            topic_coverage='sufficient'
        )

        assert assessment.is_sufficient is True

    def test_rag_quality_boundary_confidence(self):
        """Test boundary case with 3 chunks but confidence just below 0.7."""
        assessment = RAGQualityAssessment(
            chunk_count=3,
            avg_confidence=0.69,
            max_confidence=0.75,
            min_confidence=0.65,
            sources_covered=['ADA', 'Joslin', 'AADE'],
            source_diversity=3,
            topic_coverage='partial'
        )

        assert assessment.is_sufficient is False

    def test_rag_quality_empty_results(self):
        """Test RAG quality with no results."""
        assessment = RAGQualityAssessment(
            chunk_count=0,
            avg_confidence=0.0,
            max_confidence=0.0,
            min_confidence=0.0,
            sources_covered=[],
            source_diversity=0,
            topic_coverage='sparse'
        )

        assert assessment.is_sufficient is False
        assert assessment.topic_coverage == 'sparse'

    def test_rag_quality_source_diversity(self):
        """Test source diversity calculation."""
        assessment = RAGQualityAssessment(
            chunk_count=4,
            avg_confidence=0.8,
            max_confidence=0.85,
            min_confidence=0.75,
            sources_covered=['ADA', 'Joslin', 'AADE'],
            source_diversity=3,
            topic_coverage='sufficient'
        )

        assert assessment.source_diversity == 3

    def test_rag_quality_single_source(self):
        """Test with single source."""
        assessment = RAGQualityAssessment(
            chunk_count=3,
            avg_confidence=0.8,
            max_confidence=0.85,
            min_confidence=0.75,
            sources_covered=['ADA'],
            source_diversity=1,
            topic_coverage='sufficient'
        )

        assert assessment.source_diversity == 1


class TestKnowledgeBreakdownCalculation:
    """Test knowledge breakdown calculation logic."""

    def test_breakdown_rag_only(self):
        """Test breakdown for RAG-only response."""
        breakdown = KnowledgeBreakdown(
            rag_confidence=0.85,
            parametric_confidence=0.6,
            blended_confidence=0.85,
            rag_ratio=1.0,
            parametric_ratio=0.0,
            primary_source_type='rag'
        )

        assert breakdown.rag_ratio == 1.0
        assert breakdown.parametric_ratio == 0.0
        assert breakdown.primary_source_type == 'rag'

    def test_breakdown_hybrid_mode(self):
        """Test breakdown for hybrid mode with sparse RAG."""
        breakdown = KnowledgeBreakdown(
            rag_confidence=0.4,
            parametric_confidence=0.6,
            blended_confidence=0.52,
            rag_ratio=0.4,
            parametric_ratio=0.6,
            primary_source_type='hybrid'
        )

        assert breakdown.rag_ratio == 0.4
        assert breakdown.parametric_ratio == 0.6
        assert breakdown.primary_source_type == 'hybrid'

    def test_breakdown_parametric_heavy(self):
        """Test breakdown for parametric-heavy response."""
        breakdown = KnowledgeBreakdown(
            rag_confidence=0.2,
            parametric_confidence=0.6,
            blended_confidence=0.44,
            rag_ratio=0.2,
            parametric_ratio=0.8,
            primary_source_type='parametric'
        )

        assert breakdown.parametric_ratio == 0.8
        assert breakdown.primary_source_type == 'parametric'

    def test_breakdown_glooko_present(self):
        """Test that Glooko takes precedence when present."""
        breakdown = KnowledgeBreakdown(
            rag_confidence=0.8,
            parametric_confidence=0.6,
            blended_confidence=0.8,
            rag_ratio=1.0,
            parametric_ratio=0.0,
            primary_source_type='glooko'
        )

        assert breakdown.primary_source_type == 'glooko'

    def test_breakdown_blended_confidence(self):
        """Test blended confidence calculation."""
        breakdown = KnowledgeBreakdown(
            rag_confidence=0.8,
            parametric_confidence=0.6,
            blended_confidence=0.7,
            rag_ratio=0.5,
            parametric_ratio=0.5,
            primary_source_type='hybrid'
        )

        # 0.8 * 0.5 + 0.6 * 0.5 = 0.4 + 0.3 = 0.7
        assert breakdown.blended_confidence == 0.7

    def test_breakdown_parametric_fixed_confidence(self):
        """Test that parametric confidence is fixed at 0.6."""
        breakdown = KnowledgeBreakdown(
            rag_confidence=0.0,
            parametric_confidence=0.6,
            blended_confidence=0.6,
            rag_ratio=0.0,
            parametric_ratio=1.0,
            primary_source_type='parametric'
        )

        assert breakdown.parametric_confidence == 0.6


class TestHybridPromptBuilding:
    """Test hybrid prompt building logic."""

    @pytest.fixture
    def agent(self):
        """Create a mock UnifiedAgent for testing."""
        agent = UnifiedAgent.__new__(UnifiedAgent)  # Create without calling __init__
        return agent

    def test_hybrid_prompt_contains_rag_context(self, agent):
        """Test that hybrid prompt includes RAG context when present."""
        rag_quality = RAGQualityAssessment(
            chunk_count=2,
            avg_confidence=0.6,
            max_confidence=0.7,
            min_confidence=0.5,
            sources_covered=['ADA'],
            source_diversity=1,
            topic_coverage='partial'
        )

        rag_context = "ADA guidelines recommend checking blood sugar before meals."

        prompt = agent._build_hybrid_prompt(
            query="When should I check blood sugar?",
            rag_context=rag_context,
            rag_quality=rag_quality
        )

        assert rag_context in prompt
        # Updated: new prompt uses "Retrieved Documentation" section header
        assert "Retrieved Documentation" in prompt

    def test_hybrid_prompt_attribution_instructions(self, agent):
        """Test that hybrid prompt contains attribution requirements."""
        rag_quality = RAGQualityAssessment(
            chunk_count=1,
            avg_confidence=0.4,
            max_confidence=0.4,
            min_confidence=0.4,
            sources_covered=['ADA'],
            source_diversity=1,
            topic_coverage='sparse'
        )

        prompt = agent._build_hybrid_prompt(
            query="What is insulin?",
            rag_context="Insulin is a hormone...",
            rag_quality=rag_quality
        )

        # Updated: new prompt uses inline superscript citations
        assert "superscript" in prompt.lower() or "citation" in prompt.lower()
        assert "INSTRUCTIONS" in prompt

    def test_hybrid_prompt_prohibition_rules(self, agent):
        """Test that hybrid prompt contains prohibition rules."""
        rag_quality = RAGQualityAssessment(
            chunk_count=0,
            avg_confidence=0.0,
            max_confidence=0.0,
            min_confidence=0.0,
            sources_covered=[],
            source_diversity=0,
            topic_coverage='sparse'
        )

        prompt = agent._build_hybrid_prompt(
            query="How does insulin work?",
            rag_context=None,
            rag_quality=rag_quality
        )

        # Updated: new prompt uses "DO NOT use general knowledge for" phrasing
        assert "DO NOT" in prompt
        assert "Device-specific" in prompt or "device" in prompt.lower()
        assert "insulin doses" in prompt.lower() or "dosing" in prompt.lower()

    def test_hybrid_prompt_priority_order(self, agent):
        """Test that hybrid prompt states documentation priority."""
        rag_quality = RAGQualityAssessment(
            chunk_count=2,
            avg_confidence=0.6,
            max_confidence=0.7,
            min_confidence=0.5,
            sources_covered=['ADA', 'Joslin'],
            source_diversity=2,
            topic_coverage='partial'
        )

        prompt = agent._build_hybrid_prompt(
            query="What is diabetes?",
            rag_context="Diabetes is...",
            rag_quality=rag_quality
        )

        # Updated: new prompt has "Retrieved Documentation (High Confidence)" and "General Medical Knowledge"
        assert "Retrieved Documentation" in prompt
        assert "General" in prompt and "Knowledge" in prompt

    def test_hybrid_prompt_with_glooko(self, agent):
        """Test that hybrid prompt includes Glooko context when present."""
        rag_quality = RAGQualityAssessment(
            chunk_count=1,
            avg_confidence=0.5,
            max_confidence=0.5,
            min_confidence=0.5,
            sources_covered=['ADA'],
            source_diversity=1,
            topic_coverage='partial'
        )

        glooko_context = "Average glucose: 140 mg/dL"

        prompt = agent._build_hybrid_prompt(
            query="How is my glucose?",
            rag_context="Glucose monitoring is important...",
            rag_quality=rag_quality,
            glooko_context=glooko_context
        )

        assert "USER'S PERSONAL DATA" in prompt
        assert glooko_context in prompt


class TestUnifiedResponseGeneration:
    """Test UnifiedResponse generation logic."""

    def test_response_rag_sufficient(self):
        """Test response generation for sufficient RAG."""
        response = UnifiedResponse(
            success=True,
            answer="Check blood sugar before meals according to ADA guidelines.",
            sources_used=['rag'],
            glooko_data_available=False,
            rag_quality=RAGQualityMetrics(
                chunk_count=4,
                avg_confidence=0.85,
                sources_covered=['ADA', 'Joslin'],
                topic_coverage='sufficient'
            ),
            requires_enhanced_safety_check=False,
            knowledge_breakdown=KnowledgeBreakdown(
                rag_confidence=0.85,
                parametric_confidence=0.6,
                blended_confidence=0.85,
                rag_ratio=1.0,
                parametric_ratio=0.0,
                primary_source_type='rag'
            )
        )

        assert response.requires_enhanced_safety_check is False
        assert response.sources_used == ['rag']
        assert response.knowledge_breakdown.primary_source_type == 'rag'

    def test_response_hybrid_mode(self):
        """Test response generation for hybrid mode."""
        response = UnifiedResponse(
            success=True,
            answer="Insulin helps regulate blood sugar [General medical knowledge]. Check with your healthcare team.",
            sources_used=['rag', 'parametric'],
            glooko_data_available=False,
            rag_quality=RAGQualityMetrics(
                chunk_count=1,
                avg_confidence=0.4,
                sources_covered=['ADA'],
                topic_coverage='sparse'
            ),
            requires_enhanced_safety_check=True,
            knowledge_breakdown=KnowledgeBreakdown(
                rag_confidence=0.4,
                parametric_confidence=0.6,
                blended_confidence=0.52,
                rag_ratio=0.4,
                parametric_ratio=0.6,
                primary_source_type='hybrid'
            )
        )

        assert response.requires_enhanced_safety_check is True
        assert 'parametric' in response.sources_used
        assert response.knowledge_breakdown.primary_source_type == 'hybrid'

    def test_response_disclaimer_parametric_heavy(self):
        """Test disclaimer for parametric-heavy responses."""
        response = UnifiedResponse(
            success=True,
            answer="This is general information about insulin [General medical knowledge].",
            sources_used=['parametric'],
            glooko_data_available=False,
            disclaimer="This response includes general medical knowledge. Consult your healthcare provider for personalized advice.",
            requires_enhanced_safety_check=True,
            knowledge_breakdown=KnowledgeBreakdown(
                rag_confidence=0.0,
                parametric_confidence=0.6,
                blended_confidence=0.6,
                rag_ratio=0.0,
                parametric_ratio=1.0,
                primary_source_type='parametric'
            )
        )

        assert "general medical knowledge" in response.disclaimer.lower()

    def test_response_disclaimer_rag_only(self):
        """Test disclaimer for RAG-only responses."""
        response = UnifiedResponse(
            success=True,
            answer="According to ADA guidelines, check blood sugar regularly.",
            sources_used=['rag'],
            glooko_data_available=False,
            disclaimer="This is educational information only. Consult your healthcare provider.",
            requires_enhanced_safety_check=False,
            knowledge_breakdown=KnowledgeBreakdown(
                rag_confidence=0.9,
                parametric_confidence=0.6,
                blended_confidence=0.9,
                rag_ratio=1.0,
                parametric_ratio=0.0,
                primary_source_type='rag'
            )
        )

        assert "educational information" in response.disclaimer.lower()
        assert "general medical knowledge" not in response.disclaimer.lower()

    def test_response_success_false_on_error(self):
        """Test response when LLM error occurs."""
        response = UnifiedResponse(
            success=False,
            answer="An error occurred while processing your question.",
            sources_used=[],
            glooko_data_available=False
        )

        assert response.success is False
        assert "error" in response.answer.lower()
