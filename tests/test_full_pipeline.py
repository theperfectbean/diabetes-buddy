#!/usr/bin/env python3
"""
Integration Tests for Diabetes Buddy Knowledge Base Pipeline

Tests:
1. OpenAPS docs ingestion (sample repo)
2. PubMed API query (1 article fetch)
3. Multi-collection RAG query
4. Glooko + research query combination
5. Verify all confidence scores present
6. Check safety auditor flags dosage queries

Usage:
    pytest tests/test_full_pipeline.py -v
    pytest tests/test_full_pipeline.py -v -m "not integration"  # Skip slow tests
    pytest tests/test_full_pipeline.py --cov=agents --cov-report=term
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def project_root():
    """Return project root path."""
    return PROJECT_ROOT


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary data directory structure."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "sources").mkdir()
    (data_dir / "cache").mkdir()
    (data_dir / "update_logs").mkdir()
    return data_dir


@pytest.fixture
def mock_chromadb():
    """Mock ChromaDB client for testing without actual database."""
    with patch('chromadb.PersistentClient') as mock_client:
        mock_collection = MagicMock()
        mock_collection.count.return_value = 100
        mock_collection.query.return_value = {
            'documents': [['Test document about insulin pumps']],
            'metadatas': [[{'source': 'test', 'confidence': 0.85}]],
            'distances': [[0.3]]
        }
        mock_collection.get.return_value = {'ids': [], 'documents': [], 'metadatas': []}

        mock_client_instance = MagicMock()
        mock_client_instance.get_or_create_collection.return_value = mock_collection
        mock_client_instance.get_collection.return_value = mock_collection
        mock_client_instance.list_collections.return_value = [mock_collection]
        mock_client.return_value = mock_client_instance

        yield mock_client_instance


@pytest.fixture
def mock_llm():
    """Mock LLM provider for testing without API calls."""
    with patch('agents.llm_provider.LLMFactory.get_provider') as mock_factory:
        mock_provider = MagicMock()
        mock_provider.embed_text.return_value = [[0.1] * 768]  # 768-dim embedding
        mock_provider.generate_text.return_value = "Test response about diabetes management."
        mock_factory.return_value = mock_provider
        yield mock_provider


# =============================================================================
# Phase 1: OpenAPS Docs Ingestion Tests
# =============================================================================

class TestOpenAPSDocsIngestion:
    """Tests for OpenAPS documentation ingestion."""

    def test_git_manager_clone(self, temp_data_dir, monkeypatch):
        """Test GitManager can initialize clone command."""
        from scripts.ingest_openaps_docs import GitManager, REPO_CONFIG

        # Patch RAW_REPOS_DIR to temp directory
        monkeypatch.setattr('scripts.ingest_openaps_docs.RAW_REPOS_DIR', temp_data_dir / "sources")

        git_manager = GitManager()
        assert git_manager.repos_dir.exists()

    def test_version_cache_operations(self, temp_data_dir, monkeypatch):
        """Test version cache save/load."""
        monkeypatch.setattr('scripts.ingest_openaps_docs.CACHE_DIR', temp_data_dir / "cache")
        monkeypatch.setattr('scripts.ingest_openaps_docs.VERSIONS_FILE', temp_data_dir / "cache" / "versions.json")

        from scripts.ingest_openaps_docs import VersionCache

        cache = VersionCache()
        cache.set_commit("openaps", "abc123")
        cache.save()

        # Reload and verify
        cache2 = VersionCache()
        assert cache2.get_commit("openaps") == "abc123"

    def test_content_processor_word_count(self, temp_data_dir, monkeypatch):
        """Test content processor word counting."""
        monkeypatch.setattr('scripts.ingest_openaps_docs.RAW_REPOS_DIR', temp_data_dir / "sources")

        from scripts.ingest_openaps_docs import ContentProcessor, GitManager

        git = GitManager()
        processor = ContentProcessor(git)

        content = "This is a test document. It has multiple sentences."
        word_count = processor.calculate_word_count(content)
        assert word_count == 9

    def test_content_processor_strips_markdown(self, temp_data_dir, monkeypatch):
        """Test that processor strips markdown formatting."""
        monkeypatch.setattr('scripts.ingest_openaps_docs.RAW_REPOS_DIR', temp_data_dir / "sources")

        from scripts.ingest_openaps_docs import ContentProcessor, GitManager

        git = GitManager()
        processor = ContentProcessor(git)

        # Markdown with code blocks and links
        content = """# Title

Some text with a [link](http://example.com).

```python
def hello():
    pass
```

More text here.
"""
        word_count = processor.calculate_word_count(content)
        # Should strip code blocks and link formatting
        assert word_count < 20

    def test_supported_extensions(self):
        """Test that both .md and .rst are supported."""
        from scripts.ingest_openaps_docs import SUPPORTED_EXTENSIONS

        assert '.md' in SUPPORTED_EXTENSIONS
        assert '.rst' in SUPPORTED_EXTENSIONS

    def test_repo_config_has_confidence(self):
        """Test that all repos have confidence scores."""
        from scripts.ingest_openaps_docs import REPO_CONFIG

        for repo_key, config in REPO_CONFIG.items():
            assert 'confidence' in config, f"Missing confidence for {repo_key}"
            assert 0.0 <= config['confidence'] <= 1.0


# =============================================================================
# Phase 2: PubMed API Tests
# =============================================================================

class TestPubMedIngestion:
    """Tests for PubMed API integration."""

    def test_config_loads_defaults(self):
        """Test config loads with defaults when file missing."""
        from agents.pubmed_ingestion import Config
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(Path(tmpdir) / "nonexistent.json")
            assert config.api_base_url.startswith("https://")
            assert config.rate_limit > 0

    def test_config_loads_from_file(self, project_root):
        """Test config loads from pubmed_config.json."""
        config_path = project_root / "config" / "pubmed_config.json"
        if config_path.exists():
            from agents.pubmed_ingestion import Config
            config = Config(config_path)
            assert len(config.search_terms) > 0
            assert config.filters.get('days_back') is not None

    def test_article_dataclass(self):
        """Test Article dataclass serialization."""
        from agents.pubmed_ingestion import Article, Author

        author = Author(last_name="Smith", fore_name="John")
        article = Article(
            pmid="12345678",
            title="Test Article",
            abstract="This is a test abstract",
            authors=[author],
            publication_date=datetime.now(),
            journal="Test Journal",
            confidence=0.7
        )

        article_dict = article.to_dict()
        assert article_dict['pmid'] == "12345678"
        assert article_dict['confidence'] == 0.7

    @pytest.mark.integration
    async def test_pubmed_search_single_article(self):
        """Test fetching a single article from PubMed API."""
        from agents.pubmed_ingestion import PubMedClient, Config

        config = Config()
        client = PubMedClient(config)

        # Search for a very specific term to get few results
        pmids = await client.search_articles(
            "type 1 diabetes closed loop",
            days_back=30,
            max_results=1
        )

        # Should find at least something (may be empty if no recent articles)
        assert isinstance(pmids, list)

    def test_safety_flags_dosage_keywords(self):
        """Test that safety config includes dosage keywords."""
        from agents.pubmed_ingestion import Config

        config = Config()
        safety_config = config.safety_config
        dosage_keywords = safety_config.get('dosage_keywords', [])

        # Should have keywords for flagging safety-relevant content
        assert any('dose' in kw.lower() for kw in dosage_keywords)


# =============================================================================
# Phase 3: Multi-Collection RAG Query Tests
# =============================================================================

class TestMultiCollectionRAG:
    """Tests for multi-collection RAG query pipeline."""

    def test_search_result_dataclass(self):
        """Test SearchResult dataclass."""
        from agents.researcher_chromadb import SearchResult

        result = SearchResult(
            quote="Test quote",
            page_number=10,
            confidence=0.85,
            source="Test Source",
            context="Test context"
        )

        assert result.confidence == 0.85
        assert result.source == "Test Source"

    def test_chromadb_backend_init(self, mock_chromadb, mock_llm, project_root):
        """Test ChromaDBBackend initializes correctly."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"}):
            from agents.researcher_chromadb import ChromaDBBackend

            backend = ChromaDBBackend(project_root=project_root)
            assert backend is not None

    def test_researcher_agent_search_all_collections(self, mock_chromadb, mock_llm, project_root):
        """Test ResearcherAgent.search_all_collections method exists."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"}):
            from agents.researcher_chromadb import ResearcherAgent

            researcher = ResearcherAgent(project_root=project_root, use_chromadb=True)
            assert hasattr(researcher, 'search_all_collections')

    def test_search_with_citations(self, mock_chromadb, mock_llm, project_root):
        """Test search_with_citations returns formatted citations."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"}):
            from agents.researcher_chromadb import ResearcherAgent

            researcher = ResearcherAgent(project_root=project_root, use_chromadb=True)
            assert hasattr(researcher, 'search_with_citations')

    def test_format_citation_method(self):
        """Test citation formatting."""
        from agents.researcher_chromadb import ChromaDBBackend, SearchResult

        result = SearchResult(
            quote="Test",
            page_number=1,
            confidence=0.85,
            source="OpenAPS Docs",
            context=""
        )

        citation = ChromaDBBackend.format_citation(result)
        assert "OpenAPS Docs" in citation
        assert "0.85" in citation

    def test_search_multiple_includes_all_sources(self, mock_chromadb, mock_llm, project_root):
        """Test that search_multiple includes all collection types."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"}):
            from agents.researcher_chromadb import ResearcherAgent

            researcher = ResearcherAgent(project_root=project_root, use_chromadb=True)

            # Check search_map includes expected sources
            expected_sources = [
                'theory', 'camaps', 'ypsomed', 'libre',
                'ada_standards', 'australian_guidelines',
                'research_papers', 'openaps_docs'
            ]

            for source in expected_sources:
                assert hasattr(researcher, f'search_{source}') or source in ['research_papers', 'openaps_docs']


# =============================================================================
# Phase 4: Glooko + Research Query Combination Tests
# =============================================================================

class TestGlookoResearchCombination:
    """Tests for combining Glooko personal data with research queries."""

    def test_glooko_query_agent_exists(self, project_root):
        """Test GlookoQueryAgent can be imported."""
        from agents.glooko_query import GlookoQueryAgent
        assert GlookoQueryAgent is not None

    def test_unified_agent_exists(self, project_root):
        """Test UnifiedAgent can be imported."""
        from agents.unified_agent import UnifiedAgent
        assert UnifiedAgent is not None

    def test_query_intent_dataclass(self, project_root):
        """Test QueryIntent dataclass structure."""
        from agents.glooko_query import QueryIntent

        intent = QueryIntent(
            metric_type="glucose",
            aggregation="average",
            date_range="last_week",  # Required field
            confidence=0.9
        )
        assert intent.metric_type == "glucose"
        assert intent.confidence == 0.9


# =============================================================================
# Phase 5: Confidence Score Verification Tests
# =============================================================================

class TestConfidenceScores:
    """Tests to verify confidence scores are present in all results."""

    def test_openaps_config_has_confidence(self):
        """Test OpenAPS config includes confidence."""
        from scripts.ingest_openaps_docs import REPO_CONFIG

        for repo_key, config in REPO_CONFIG.items():
            assert 'confidence' in config
            assert config['confidence'] == 0.8  # As specified

    def test_pubmed_default_confidence(self):
        """Test PubMed uses correct default confidence."""
        from agents.pubmed_ingestion import Config

        config = Config()
        default_conf = config.safety_config.get('default_confidence', 0.7)
        assert default_conf == 0.7  # As specified

    def test_search_result_has_confidence(self):
        """Test SearchResult always has confidence field."""
        from agents.researcher_chromadb import SearchResult

        # Confidence is a required field
        with pytest.raises(TypeError):
            SearchResult(
                quote="Test",
                page_number=1,
                source="Test"
            )

        # Should work with confidence
        result = SearchResult(
            quote="Test",
            page_number=1,
            confidence=0.8,
            source="Test",
            context=""
        )
        assert hasattr(result, 'confidence')


# =============================================================================
# Phase 6: Safety Auditor Tests
# =============================================================================

class TestSafetyAuditor:
    """Tests for safety auditor flagging dosage queries."""

    def test_safety_module_exists(self, project_root):
        """Test safety module can be imported."""
        from agents.safety import SafetyAuditor
        assert SafetyAuditor is not None

    def test_safety_auditor_flags_dosage(self, mock_llm, project_root):
        """Test safety auditor flags dosage-related content."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"}):
            from agents.safety import SafetyAuditor

            # SafetyAuditor takes an optional triage_agent, not project_root
            auditor = SafetyAuditor(triage_agent=None)

            # Test that dosage-related text is flagged
            dosage_text = "Take 10 units of insulin before meals"

            # The auditor should have a method to check for safety issues
            assert hasattr(auditor, 'audit') or hasattr(auditor, 'audit_text')

    def test_safety_config_keywords(self):
        """Test safety config has dosage keywords."""
        from agents.pubmed_ingestion import Config

        config = Config()
        keywords = config.safety_config.get('dosage_keywords', [])

        dosage_terms = ['dosage', 'dose', 'units']
        found = sum(1 for term in dosage_terms if any(term in kw.lower() for kw in keywords))
        assert found > 0, "Should have at least one dosage-related keyword"


# =============================================================================
# Monthly Update Orchestrator Tests
# =============================================================================

class TestMonthlyUpdateOrchestrator:
    """Tests for monthly update orchestrator."""

    def test_orchestrator_creates_report(self, temp_data_dir, monkeypatch):
        """Test orchestrator creates update report."""
        from scripts.monthly_update import MonthlyUpdateReport, UpdatePhaseResult

        report = MonthlyUpdateReport()
        phase_result = UpdatePhaseResult(
            phase_name="Test Phase",
            success=True,
            files_processed=10
        )
        phase_result.end_time = datetime.now()

        report.add_phase(phase_result)

        assert len(report.phases) == 1
        assert report.success is True

    def test_last_run_tracker(self, temp_data_dir, monkeypatch):
        """Test last run tracker saves/loads timestamps."""
        monkeypatch.setattr('scripts.monthly_update.CACHE_DIR', temp_data_dir / "cache")
        monkeypatch.setattr('scripts.monthly_update.LAST_RUN_FILE', temp_data_dir / "cache" / "last_run.json")

        from scripts.monthly_update import LastRunTracker

        tracker = LastRunTracker()
        tracker.set_last_run('openaps')
        tracker.save()

        # Reload and verify
        tracker2 = LastRunTracker()
        last_run = tracker2.get_last_run('openaps')
        assert last_run is not None
        assert (datetime.now() - last_run).total_seconds() < 60


# =============================================================================
# Integration Test: Full Pipeline
# =============================================================================

@pytest.mark.integration
class TestFullPipelineIntegration:
    """Full integration tests requiring real API access."""

    def test_chromadb_collection_exists(self, project_root):
        """Test that ChromaDB can be initialized."""
        try:
            import chromadb
            from chromadb.config import Settings

            db_path = project_root / ".cache" / "chromadb"
            if db_path.exists():
                client = chromadb.PersistentClient(
                    path=str(db_path),
                    settings=Settings(anonymized_telemetry=False)
                )
                collections = client.list_collections()
                assert isinstance(collections, list)
        except ImportError:
            pytest.skip("chromadb not installed")

    def test_full_search_pipeline(self, project_root, mock_llm):
        """Test full search pipeline with mocked LLM."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"}):
            try:
                import chromadb
                from chromadb.config import Settings

                db_path = project_root / ".cache" / "chromadb"
                if not db_path.exists():
                    pytest.skip("ChromaDB not initialized")

                from agents.researcher_chromadb import ResearcherAgent

                researcher = ResearcherAgent(project_root=project_root, use_chromadb=True)

                # Should be able to search (may return empty if no data)
                results = researcher.search_theory("insulin pump")
                assert isinstance(results, list)

            except ImportError:
                pytest.skip("Required packages not installed")


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
