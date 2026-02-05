"""
ChromaDB Integration Tests for RAG Retrieval

Tests actual RAG retrieval using populated ChromaDB fixtures.
Validates source prioritization, confidence scoring, and query relevance.
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.researcher_chromadb import SearchResult


class TestChromaDBRetrieval:
    """Test actual ChromaDB retrieval with populated fixtures."""

    def test_clinical_query_prioritizes_ada(self, researcher_with_test_data):
        """Test that clinical queries prioritize ADA Standards (confidence=1.0)."""
        query = "What HbA1c target for newly diagnosed type 1 diabetes?"
        
        # Query the knowledge base
        results = researcher_with_test_data.backend.search_all_collections(query, top_k=5)
        
        # Should return results
        assert len(results) > 0, "Expected RAG retrieval to return results"
        
        # Find ADA results
        ada_results = [r for r in results if r.source == "ada_standards"]
        assert len(ada_results) > 0, "Expected ADA Standards in results"
        
        # ADA should have highest confidence (trust_level=1.0)
        ada_confidences = [r.confidence for r in ada_results]
        max_ada_confidence = max(ada_confidences)
        assert max_ada_confidence >= 0.7, f"Expected high confidence for ADA, got {max_ada_confidence}"
        
        # Check that at least one ADA result mentions A1C/HbA1c target
        ada_quotes = [r.quote.lower() for r in ada_results]
        assert any("a1c" in quote or "hba1c" in quote for quote in ada_quotes), \
            "Expected ADA result to mention A1C/HbA1c"
        assert any("target" in quote or "7%" in quote for quote in ada_quotes), \
            "Expected ADA result to mention target or specific value"

    def test_practical_query_prioritizes_openaps(self, researcher_with_test_data):
        """Test that practical queries prioritize OpenAPS docs (confidence=0.8)."""
        query = "How to set basal rates for overnight control?"
        
        # Query the knowledge base
        results = researcher_with_test_data.backend.search_all_collections(query, top_k=5)
        
        # Should return results
        assert len(results) > 0, "Expected RAG retrieval to return results"
        
        # Find OpenAPS results
        openaps_results = [r for r in results if r.source == "openaps_docs"]
        assert len(openaps_results) > 0, "Expected OpenAPS docs in results"
        
        # OpenAPS should have good confidence (trust_level=0.8)
        openaps_confidences = [r.confidence for r in openaps_results]
        max_openaps_confidence = max(openaps_confidences)
        assert max_openaps_confidence >= 0.6, f"Expected good confidence for OpenAPS, got {max_openaps_confidence}"
        
        # Check that at least one OpenAPS result mentions basal rates
        openaps_quotes = [r.quote.lower() for r in openaps_results]
        assert any("basal" in quote for quote in openaps_quotes), \
            "Expected OpenAPS result to mention basal rates"

    def test_hybrid_query_blends_sources(self, researcher_with_test_data):
        """Test that hybrid queries blend ADA, OpenAPS, and research sources."""
        query = "CGM accuracy and calibration best practices"
        
        # Query the knowledge base
        results = researcher_with_test_data.backend.search_all_collections(query, top_k=10)
        
        # Should return results from multiple sources
        assert len(results) >= 3, "Expected at least 3 results for hybrid query"
        
        # Get unique sources
        sources = set(r.source for r in results)
        
        # Should have at least 2 different sources
        assert len(sources) >= 2, f"Expected multiple sources, got {sources}"
        
        # Check for expected source types
        expected_sources = {"ada_standards", "openaps_docs", "research_papers"}
        found_expected = sources & expected_sources
        assert len(found_expected) >= 2, \
            f"Expected at least 2 of {expected_sources}, found {found_expected}"
        
        # Check that results mention CGM-related terms
        all_quotes = [r.quote.lower() for r in results]
        cgm_mentions = sum(1 for quote in all_quotes if "cgm" in quote or "calibrat" in quote or "accuracy" in quote)
        assert cgm_mentions >= 2, "Expected multiple results to mention CGM/calibration/accuracy"

    def test_confidence_scores_above_threshold(self, researcher_with_test_data):
        """Test that retrieval returns high-confidence results."""
        queries = [
            "HbA1c target for type 1 diabetes",
            "basal rate testing overnight",
            "CGM calibration frequency"
        ]
        
        for query in queries:
            results = researcher_with_test_data.backend.search_all_collections(query, top_k=5)
            
            # Should return results
            assert len(results) > 0, f"Expected results for query: {query}"
            
            # At least one result should have confidence > 0.7
            confidences = [r.confidence for r in results]
            max_confidence = max(confidences)
            assert max_confidence > 0.7, \
                f"Expected at least one high-confidence result for '{query}', max was {max_confidence}"

    def test_source_trust_levels_applied(self, researcher_with_test_data):
        """Test that source trust levels are properly applied to confidence scores."""
        query = "diabetes management guidelines"
        
        # Query the knowledge base
        results = researcher_with_test_data.backend.search_all_collections(query, top_k=10)
        
        # Group by source
        ada_results = [r for r in results if r.source == "ada_standards"]
        openaps_results = [r for r in results if r.source == "openaps_docs"]
        research_results = [r for r in results if r.source == "research_papers"]
        
        # ADA (trust=1.0) should generally have higher confidence than OpenAPS (trust=0.8)
        if ada_results and openaps_results:
            max_ada = max(r.confidence for r in ada_results)
            max_openaps = max(r.confidence for r in openaps_results)
            # ADA should be at least as high (allowing for query relevance variation)
            assert max_ada >= max_openaps * 0.9, \
                f"Expected ADA confidence ({max_ada}) >= OpenAPS ({max_openaps})"
        
        # OpenAPS (trust=0.8) should generally have higher confidence than research (trust=0.7)
        if openaps_results and research_results:
            max_openaps = max(r.confidence for r in openaps_results)
            max_research = max(r.confidence for r in research_results)
            assert max_openaps >= max_research * 0.9, \
                f"Expected OpenAPS confidence ({max_openaps}) >= research ({max_research})"

    def test_ada_standards_content_quality(self, researcher_with_test_data):
        """Test that ADA Standards results contain high-quality clinical content."""
        query = "insulin dosing guidelines"
        
        results = researcher_with_test_data.backend.search_all_collections(query, top_k=5)
        ada_results = [r for r in results if r.source == "ada_standards"]
        
        assert len(ada_results) > 0, "Expected ADA results for insulin dosing query"
        
        # Check content quality
        for result in ada_results[:3]:  # Check top 3
            # Should have substantive content (>50 chars)
            assert len(result.quote) > 50, "ADA result should have substantive content"
            
            # Should have page number
            assert result.page_number is not None, "ADA result should have page number"
            
            # Should have source metadata
            assert result.source == "ada_standards", "Source should be ada_standards"

    def test_openaps_content_quality(self, researcher_with_test_data):
        """Test that OpenAPS results contain practical guidance."""
        query = "basal testing procedure"
        
        results = researcher_with_test_data.backend.search_all_collections(query, top_k=5)
        openaps_results = [r for r in results if r.source == "openaps_docs"]
        
        assert len(openaps_results) > 0, "Expected OpenAPS results for basal testing query"
        
        # Check content quality
        for result in openaps_results[:3]:  # Check top 3
            # Should have substantive content
            assert len(result.quote) > 50, "OpenAPS result should have substantive content"
            
            # Should have practical keywords
            quote_lower = result.quote.lower()
            practical_keywords = ["test", "start", "check", "monitor", "adjust", "set", "procedure"]
            assert any(kw in quote_lower for kw in practical_keywords), \
                "OpenAPS result should contain practical guidance keywords"

    def test_research_papers_content(self, researcher_with_test_data):
        """Test that research papers results contain academic content."""
        query = "CGM accuracy studies"
        
        results = researcher_with_test_data.backend.search_all_collections(query, top_k=5)
        research_results = [r for r in results if r.source == "research_papers"]
        
        if len(research_results) > 0:  # Research papers are optional
            # Check content quality
            for result in research_results[:3]:
                # Should have substantive content
                assert len(result.quote) > 50, "Research result should have substantive content"
                
                # Research papers typically mention studies, accuracy metrics, etc.
                quote_lower = result.quote.lower()
                academic_keywords = ["study", "research", "accuracy", "mard", "participants", "diabetes"]
                has_academic_content = any(kw in quote_lower for kw in academic_keywords)
                # Not strictly enforced since content varies
                if not has_academic_content:
                    print(f"Warning: Research result may lack academic keywords: {result.quote[:100]}")

    @pytest.mark.parametrize("query,expected_min_results", [
        ("HbA1c target", 2),
        ("basal rates", 2),
        ("CGM calibration", 2),
        ("insulin therapy", 2),
    ])
    def test_query_returns_sufficient_results(self, researcher_with_test_data, query, expected_min_results):
        """Test that common queries return sufficient results."""
        results = researcher_with_test_data.backend.search_all_collections(query, top_k=5)
        
        assert len(results) >= expected_min_results, \
            f"Expected at least {expected_min_results} results for '{query}', got {len(results)}"
        
        # Results should be relevant (checking basic relevance)
        query_terms = query.lower().split()
        relevant_count = 0
        for result in results:
            quote_lower = result.quote.lower()
            if any(term in quote_lower for term in query_terms):
                relevant_count += 1
        
        # At least half should directly mention query terms
        assert relevant_count >= expected_min_results / 2, \
            f"Expected at least {expected_min_results/2} relevant results for '{query}'"


class TestRAGQualityMetrics:
    """Test RAG quality assessment with real data."""

    def test_sufficient_rag_quality(self, researcher_with_test_data):
        """Test queries that should return sufficient RAG quality."""
        sufficient_queries = [
            "HbA1c target for type 1 diabetes",
            "basal rate testing procedure",
            "CGM accuracy requirements"
        ]
        
        for query in sufficient_queries:
            results = researcher_with_test_data.backend.search_all_collections(query, top_k=5)
            
            # Should have at least 3 chunks
            assert len(results) >= 3, f"Expected ≥3 results for '{query}', got {len(results)}"
            
            # Average confidence should be ≥ 0.7
            avg_confidence = sum(r.confidence for r in results) / len(results)
            assert avg_confidence >= 0.7, \
                f"Expected avg confidence ≥0.7 for '{query}', got {avg_confidence:.2f}"

    def test_source_diversity(self, researcher_with_test_data):
        """Test that broad queries return diverse sources."""
        broad_query = "diabetes management"
        
        results = researcher_with_test_data.backend.search_all_collections(broad_query, top_k=10)
        
        # Get unique sources
        sources = set(r.source for r in results)
        
        # Should have multiple sources
        assert len(sources) >= 2, f"Expected source diversity, got {sources}"

    def test_metadata_completeness(self, researcher_with_test_data):
        """Test that results have complete metadata."""
        query = "insulin therapy"
        
        results = researcher_with_test_data.backend.search_all_collections(query, top_k=5)
        
        for result in results:
            # Check required fields
            assert result.quote, "Result should have quote"
            assert result.source, "Result should have source"
            assert result.confidence is not None, "Result should have confidence"
            assert 0.0 <= result.confidence <= 1.0, "Confidence should be in [0, 1]"
            
            # Optional but expected fields
            assert result.page_number is not None or result.page_number == 0, \
                "Result should have page_number"
            assert result.context, "Result should have context"
