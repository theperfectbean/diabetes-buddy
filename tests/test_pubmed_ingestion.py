"""
Unit tests for PubMed Auto-Ingestion Pipeline.

Run with: pytest tests/test_pubmed_ingestion.py -v
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.pubmed_ingestion import (
    ADA_STANDARDS_2026_PMC_IDS,
    Article,
    ArticleProcessor,
    ArticleSection,
    Author,
    Config,
    FullTextArticle,
    IngestionStats,
    KnowledgeBaseIntegration,
    PMCFullTextFetcher,
    PubMedClient,
    PubMedIngestionPipeline,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_author():
    """Create a sample author."""
    return Author(
        last_name="Smith",
        fore_name="John",
        initials="J",
        affiliation="University Hospital"
    )


@pytest.fixture
def sample_article(sample_author):
    """Create a sample article for testing."""
    return Article(
        pmid="12345678",
        title="Hybrid Closed Loop Systems in Type 1 Diabetes Management",
        abstract="This study evaluates the efficacy of hybrid closed loop insulin delivery systems in patients with type 1 diabetes. Results show improved time in range and reduced hypoglycemia.",
        authors=[sample_author],
        publication_date=datetime.now() - timedelta(days=2),
        journal="Diabetes Care",
        doi="10.1234/dc.2024.12345",
        pmc_id="PMC9876543",
        keywords=["diabetes", "insulin pump", "closed loop"],
        mesh_terms=["Diabetes Mellitus, Type 1", "Insulin Infusion Systems"],
        language="eng",
        is_open_access=True
    )


@pytest.fixture
def sample_config():
    """Create a sample configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "pubmed_config.json"
        config_data = {
            "api": {
                "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
                "api_key_env": "PUBMED_API_KEY",
                "rate_limit_per_second": 3,
                "rate_limit_with_key": 10,
                "timeout_seconds": 30,
                "max_retries": 3,
                "retry_delay_seconds": 1
            },
            "search_terms": ["hybrid closed loop diabetes", "insulin pump"],
            "filters": {
                "days_back": 7,
                "max_results_per_query": 50,
                "language": "english",
                "require_abstract": True,
                "min_relevance_score": 0.6,
                "open_access_only": False
            },
            "relevance_keywords": {
                "high_weight": ["type 1 diabetes", "insulin pump", "closed loop"],
                "medium_weight": ["diabetes", "glucose"],
                "low_weight": ["insulin"]
            },
            "safety": {
                "disclaimer": "Research summary. Consult healthcare provider.",
                "dosage_keywords": ["dosage", "dose adjustment"],
                "default_confidence": 0.7
            },
            "storage": {
                "research_papers_dir": "docs/research-papers",
                "clinical_guidelines_dir": "docs/clinical-guidelines/ada-standards-2026",
                "cache_dir": "data/cache",
                "processed_pmids_file": "data/cache/pubmed_processed.json",
                "processed_pmc_file": "data/cache/pmc_processed.json",
                "index_file": "docs/research-papers/index.json"
            },
            "pmc": {
                "fetch_full_text": False,
                "clinical_guidelines": {
                    "ada_standards_2026": ["PMC12690167", "PMC12690173"]
                }
            }
        }
        with open(config_path, 'w') as f:
            json.dump(config_data, f)

        yield Config(config_path)


@pytest.fixture
def temp_storage():
    """Create temporary storage directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        (tmpdir / "docs" / "research-papers").mkdir(parents=True)
        (tmpdir / "data" / "cache").mkdir(parents=True)
        yield tmpdir


# =============================================================================
# Author Tests
# =============================================================================

class TestAuthor:
    """Tests for Author dataclass."""

    def test_author_str_with_full_name(self, sample_author):
        """Test string representation with full name."""
        assert str(sample_author) == "Smith, John"

    def test_author_str_last_name_only(self):
        """Test string representation with last name only."""
        author = Author(last_name="Jones")
        assert str(author) == "Jones"


# =============================================================================
# Article Tests
# =============================================================================

class TestArticle:
    """Tests for Article dataclass."""

    def test_article_to_dict(self, sample_article):
        """Test article serialization to dictionary."""
        data = sample_article.to_dict()

        assert data['pmid'] == "12345678"
        assert data['title'] == "Hybrid Closed Loop Systems in Type 1 Diabetes Management"
        assert data['doi'] == "10.1234/dc.2024.12345"
        assert data['is_open_access'] is True
        assert len(data['authors']) == 1
        assert data['authors'][0] == "Smith, John"

    def test_article_default_values(self, sample_author):
        """Test article with minimal required fields."""
        article = Article(
            pmid="99999",
            title="Test Article",
            abstract="Test abstract",
            authors=[sample_author],
            publication_date=datetime.now(),
            journal="Test Journal"
        )

        assert article.doi is None
        assert article.pmc_id is None
        assert article.is_open_access is False
        assert article.relevance_score == 0.0
        assert article.confidence == 0.7


# =============================================================================
# Config Tests
# =============================================================================

class TestConfig:
    """Tests for Config class."""

    def test_load_config_from_file(self, sample_config):
        """Test loading configuration from file."""
        assert sample_config.api_base_url == "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        assert sample_config.rate_limit == 3  # No API key set
        assert len(sample_config.search_terms) == 2

    def test_config_defaults_when_file_missing(self):
        """Test default configuration when file doesn't exist."""
        config = Config(Path("/nonexistent/config.json"))
        assert config.api_base_url == "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        assert len(config.search_terms) > 0

    def test_rate_limit_with_api_key(self, sample_config):
        """Test rate limit increases with API key."""
        with patch.dict('os.environ', {'PUBMED_API_KEY': 'test_key'}):
            config = Config(sample_config.config_path)
            assert config.rate_limit == 10


# =============================================================================
# ArticleProcessor Tests
# =============================================================================

class TestArticleProcessor:
    """Tests for ArticleProcessor class."""

    def test_filter_articles_by_language(self, sample_config, sample_article):
        """Test filtering articles by language."""
        processor = ArticleProcessor(sample_config)

        # English article should pass
        result = processor.filter_articles([sample_article])
        assert len(result) == 1

        # Non-English article should be filtered
        sample_article.language = "ger"
        result = processor.filter_articles([sample_article])
        assert len(result) == 0

    def test_filter_articles_by_abstract(self, sample_config, sample_article):
        """Test filtering articles without abstracts."""
        processor = ArticleProcessor(sample_config)

        # Article without abstract should be filtered
        sample_article.abstract = ""
        result = processor.filter_articles([sample_article])
        assert len(result) == 0

    def test_filter_articles_by_date(self, sample_config, sample_article):
        """Test filtering articles by publication date."""
        processor = ArticleProcessor(sample_config)

        # Old article should be filtered (config has days_back=7)
        sample_article.publication_date = datetime.now() - timedelta(days=30)
        result = processor.filter_articles([sample_article])
        assert len(result) == 0

    def test_relevance_scoring(self, sample_config, sample_article):
        """Test relevance score calculation."""
        processor = ArticleProcessor(sample_config)

        # Article with high-weight keywords should score well
        result = processor.filter_articles([sample_article])
        assert len(result) == 1
        assert result[0].relevance_score > 0.6

    def test_safety_flag_detection(self, sample_config, sample_article):
        """Test detection of dosage-related content."""
        processor = ArticleProcessor(sample_config)

        # Article without dosage info
        result = processor.filter_articles([sample_article])
        assert result[0].requires_safety_review is False

        # Article with dosage info should be flagged
        sample_article.abstract = "This study recommends a dosage adjustment of 2 units."
        result = processor.filter_articles([sample_article])
        assert result[0].requires_safety_review is True

    def test_generate_structured_json(self, sample_config, sample_article):
        """Test JSON generation for article."""
        processor = ArticleProcessor(sample_config)
        json_data = processor.generate_structured_json(sample_article)

        assert json_data['pmid'] == sample_article.pmid
        assert json_data['source'] == 'pubmed'
        assert 'disclaimer' in json_data
        assert 'ingested_at' in json_data
        assert json_data['source_url'] == f"https://pubmed.ncbi.nlm.nih.gov/{sample_article.pmid}/"

    def test_generate_markdown_summary(self, sample_config, sample_article):
        """Test markdown summary generation."""
        processor = ArticleProcessor(sample_config)
        md = processor.generate_markdown_summary(sample_article)

        assert sample_article.title in md
        assert "Disclaimer" in md
        assert sample_article.pmid in md
        assert "## Abstract" in md


# =============================================================================
# KnowledgeBaseIntegration Tests
# =============================================================================

class TestKnowledgeBaseIntegration:
    """Tests for KnowledgeBaseIntegration class."""

    def test_deduplication(self, temp_storage):
        """Test duplicate detection."""
        # Create config pointing to temp storage
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                "storage": {
                    "research_papers_dir": str(temp_storage / "docs" / "research-papers"),
                    "cache_dir": str(temp_storage / "data" / "cache"),
                    "processed_pmids_file": str(temp_storage / "data" / "cache" / "pubmed_processed.json"),
                    "index_file": str(temp_storage / "docs" / "research-papers" / "index.json")
                },
                "api": {},
                "filters": {},
                "safety": {}
            }
            json.dump(config_data, f)
            config_path = f.name

        config = Config(Path(config_path))

        # Override storage paths to use temp directory
        kb = KnowledgeBaseIntegration(config)
        kb.research_dir = temp_storage / "docs" / "research-papers"
        kb.cache_dir = temp_storage / "data" / "cache"
        kb.processed_file = temp_storage / "data" / "cache" / "pubmed_processed.json"

        # First check - not a duplicate
        assert kb.is_duplicate("12345") is False

        # Add to processed
        kb._processed_pmids.add("12345")

        # Now it's a duplicate
        assert kb.is_duplicate("12345") is True

    def test_filter_duplicates(self, sample_article, temp_storage):
        """Test filtering duplicates from article list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                "storage": {
                    "research_papers_dir": str(temp_storage / "docs" / "research-papers"),
                    "cache_dir": str(temp_storage / "data" / "cache"),
                    "processed_pmids_file": str(temp_storage / "data" / "cache" / "pubmed_processed.json"),
                    "index_file": str(temp_storage / "docs" / "research-papers" / "index.json")
                },
                "api": {},
                "filters": {},
                "safety": {}
            }
            json.dump(config_data, f)
            config_path = f.name

        config = Config(Path(config_path))
        kb = KnowledgeBaseIntegration(config)
        kb.research_dir = temp_storage / "docs" / "research-papers"
        kb.cache_dir = temp_storage / "data" / "cache"
        kb.processed_file = temp_storage / "data" / "cache" / "pubmed_processed.json"

        # Pre-mark one PMID as processed
        kb._processed_pmids.add("12345678")

        articles = [sample_article]
        new_articles, duplicates = kb.filter_duplicates(articles)

        assert len(new_articles) == 0
        assert duplicates == 1


# =============================================================================
# PubMedClient Tests
# =============================================================================

class TestPubMedClient:
    """Tests for PubMedClient class."""

    def test_client_initialization(self, sample_config):
        """Test client initializes with correct settings."""
        client = PubMedClient(sample_config)

        assert client.base_url == "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        assert client._request_interval > 0

    def test_rate_limit_calculation(self, sample_config):
        """Test rate limit interval is calculated correctly."""
        client = PubMedClient(sample_config)

        # Without API key: 3 req/sec = 0.333s interval
        expected_interval = 1.0 / 3
        assert abs(client._request_interval - expected_interval) < 0.01

    def test_filter_open_access(self, sample_config, sample_article):
        """Test filtering for open access articles."""
        client = PubMedClient(sample_config)

        # Create a non-open-access article
        non_oa_article = Article(
            pmid="99999",
            title="Non-OA Article",
            abstract="Abstract",
            authors=[],
            publication_date=datetime.now(),
            journal="Journal",
            is_open_access=False
        )

        articles = [sample_article, non_oa_article]
        oa_only = client.filter_open_access_only(articles)

        assert len(oa_only) == 1
        assert oa_only[0].pmid == sample_article.pmid


# =============================================================================
# IngestionStats Tests
# =============================================================================

class TestIngestionStats:
    """Tests for IngestionStats dataclass."""

    def test_stats_to_dict(self):
        """Test stats serialization."""
        stats = IngestionStats(
            search_term="diabetes",
            articles_found=100,
            articles_added=10,
            articles_skipped_duplicate=5
        )
        stats.end_time = datetime.now()

        data = stats.to_dict()

        assert data['search_term'] == "diabetes"
        assert data['articles_found'] == 100
        assert data['articles_added'] == 10
        assert 'duration_seconds' in data


# =============================================================================
# XML Parsing Tests
# =============================================================================

class TestXMLParsing:
    """Tests for PubMed XML parsing."""

    def test_parse_article_xml(self, sample_config):
        """Test parsing PubMed XML response."""
        client = PubMedClient(sample_config)

        xml_response = """<?xml version="1.0" ?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345678</PMID>
                    <Article>
                        <ArticleTitle>Test Article Title</ArticleTitle>
                        <Abstract>
                            <AbstractText>This is a test abstract.</AbstractText>
                        </Abstract>
                        <AuthorList>
                            <Author>
                                <LastName>Smith</LastName>
                                <ForeName>John</ForeName>
                                <Initials>J</Initials>
                            </Author>
                        </AuthorList>
                        <Journal>
                            <Title>Test Journal</Title>
                        </Journal>
                        <Language>eng</Language>
                        <ELocationID EIdType="doi">10.1234/test</ELocationID>
                        <ArticleDate DateType="Electronic">
                            <Year>2024</Year>
                            <Month>01</Month>
                            <Day>15</Day>
                        </ArticleDate>
                        <PubDate>
                            <Year>2024</Year>
                            <Month>Jan</Month>
                            <Day>15</Day>
                        </PubDate>
                    </Article>
                    <KeywordList>
                        <Keyword>diabetes</Keyword>
                        <Keyword>insulin</Keyword>
                    </KeywordList>
                </MedlineCitation>
                <PubmedData>
                    <ArticleIdList>
                        <ArticleId IdType="pmc">PMC9999999</ArticleId>
                    </ArticleIdList>
                </PubmedData>
            </PubmedArticle>
        </PubmedArticleSet>
        """

        articles = client._parse_article_xml(xml_response)

        assert len(articles) == 1
        article = articles[0]

        assert article.pmid == "12345678"
        assert article.title == "Test Article Title"
        assert article.abstract == "This is a test abstract."
        assert len(article.authors) == 1
        assert str(article.authors[0]) == "Smith, John"
        assert article.journal == "Test Journal"
        assert article.doi == "10.1234/test"
        assert article.pmc_id == "PMC9999999"
        assert article.is_open_access is True
        assert "diabetes" in article.keywords

    def test_parse_empty_xml(self, sample_config):
        """Test parsing empty XML response."""
        client = PubMedClient(sample_config)

        xml_response = """<?xml version="1.0" ?>
        <PubmedArticleSet>
        </PubmedArticleSet>
        """

        articles = client._parse_article_xml(xml_response)
        assert len(articles) == 0

    def test_parse_malformed_xml(self, sample_config):
        """Test handling malformed XML gracefully."""
        client = PubMedClient(sample_config)

        xml_response = "not valid xml <>"

        articles = client._parse_article_xml(xml_response)
        assert len(articles) == 0


# =============================================================================
# Integration Tests
# =============================================================================

class TestPubMedIngestionPipeline:
    """Integration tests for the full pipeline."""

    def test_pipeline_initialization(self, sample_config):
        """Test pipeline initializes correctly."""
        pipeline = PubMedIngestionPipeline(sample_config)

        assert pipeline.client is not None
        assert pipeline.processor is not None
        assert pipeline.kb is not None

    def test_get_summary_empty(self, sample_config):
        """Test summary with no runs."""
        pipeline = PubMedIngestionPipeline(sample_config)
        summary = pipeline.get_summary()

        assert summary['search_terms_processed'] == 0
        assert summary['total_articles_found'] == 0
        assert summary['total_articles_added'] == 0

    def test_get_summary_with_stats(self, sample_config):
        """Test summary with recorded stats."""
        pipeline = PubMedIngestionPipeline(sample_config)

        stats1 = IngestionStats(
            search_term="term1",
            articles_found=50,
            articles_added=10,
            articles_skipped_duplicate=5,
            articles_flagged_safety=2
        )
        stats1.end_time = datetime.now()

        stats2 = IngestionStats(
            search_term="term2",
            articles_found=30,
            articles_added=8,
            articles_skipped_duplicate=2,
            articles_flagged_safety=1
        )
        stats2.end_time = datetime.now()

        pipeline.stats = [stats1, stats2]
        summary = pipeline.get_summary()

        assert summary['search_terms_processed'] == 2
        assert summary['total_articles_found'] == 80
        assert summary['total_articles_added'] == 18
        assert summary['total_skipped_duplicates'] == 7
        assert summary['total_flagged_safety'] == 3


# =============================================================================
# PMC Full-Text Tests
# =============================================================================

class TestADAStandardsConstants:
    """Tests for ADA Standards 2026 PMC IDs."""

    def test_ada_standards_defined(self):
        """Test that ADA Standards PMC IDs are defined."""
        assert len(ADA_STANDARDS_2026_PMC_IDS) > 0

    def test_ada_standards_has_required_sections(self):
        """Test that key ADA Standards sections are present."""
        required_sections = [
            'summary_of_revisions',
            'diabetes_technology',
            'glycemic_goals'
        ]
        for section in required_sections:
            assert section in ADA_STANDARDS_2026_PMC_IDS

    def test_ada_standards_pmc_id_format(self):
        """Test that all PMC IDs have correct format."""
        for section, pmc_id in ADA_STANDARDS_2026_PMC_IDS.items():
            assert pmc_id.startswith('PMC'), f"Invalid PMC ID format for {section}: {pmc_id}"
            assert len(pmc_id) > 3, f"PMC ID too short for {section}: {pmc_id}"


class TestFullTextArticle:
    """Tests for FullTextArticle dataclass."""

    @pytest.fixture
    def sample_full_text_article(self):
        """Create a sample full-text article."""
        return FullTextArticle(
            pmc_id="PMC12345678",
            title="Test Clinical Guideline",
            abstract="This is a test abstract for clinical guidelines.",
            authors=["Smith, John", "Doe, Jane"],
            publication_date=datetime.now(),
            journal="Diabetes Care",
            sections={
                "Introduction": "This is the introduction.",
                "Methods": "These are the methods.",
                "Results": "These are the results.",
                "Discussion": "This is the discussion."
            },
            recommendations=[
                "1. Recommendation one (Grade A)",
                "2. Recommendation two (Grade B)"
            ],
            evidence_grades={
                "1. Recommendation one (Grade A)": "A",
                "2. Recommendation two (Grade B)": "B"
            },
            references=["Reference 1", "Reference 2"],
            article_type="clinical_guideline",
            confidence=1.0,
            doi="10.1234/test",
            pmid="87654321"
        )

    def test_full_text_article_to_dict(self, sample_full_text_article):
        """Test full-text article serialization."""
        data = sample_full_text_article.to_dict()

        assert data['pmc_id'] == "PMC12345678"
        assert data['title'] == "Test Clinical Guideline"
        assert data['article_type'] == "clinical_guideline"
        assert data['confidence'] == 1.0
        assert len(data['sections']) == 4
        assert len(data['recommendations']) == 2
        assert len(data['evidence_grades']) == 2

    def test_full_text_article_defaults(self):
        """Test full-text article with minimal fields."""
        article = FullTextArticle(
            pmc_id="PMC99999",
            title="Minimal Article",
            abstract="Minimal abstract",
            authors=[],
            publication_date=datetime.now(),
            journal="Test Journal"
        )

        assert article.article_type == "research"
        assert article.confidence == 0.7
        assert article.sections == {}
        assert article.recommendations == []
        assert article.evidence_grades == {}


class TestPMCFullTextFetcher:
    """Tests for PMCFullTextFetcher class."""

    @pytest.fixture
    def pmc_fetcher(self, sample_config):
        """Create a PMC fetcher instance."""
        client = PubMedClient(sample_config)
        return PMCFullTextFetcher(client, sample_config)

    def test_fetcher_initialization(self, pmc_fetcher, sample_config):
        """Test fetcher initializes correctly."""
        assert pmc_fetcher.config == sample_config
        assert pmc_fetcher.client is not None

    def test_generate_title_slug(self, pmc_fetcher):
        """Test title slug generation."""
        # Normal title
        slug = pmc_fetcher.generate_title_slug("Diabetes Management Guidelines")
        assert slug == "diabetes-management-guidelines"

        # Title with special characters
        slug = pmc_fetcher.generate_title_slug("Type 1 Diabetes: A Review (2024)")
        assert slug == "type-1-diabetes-a-review-2024"

        # Long title (should be truncated)
        long_title = "A" * 100
        slug = pmc_fetcher.generate_title_slug(long_title)
        assert len(slug) <= 50

    def test_extract_text(self, pmc_fetcher):
        """Test text extraction from XML elements."""
        from xml.etree import ElementTree

        # Simple element
        elem = ElementTree.fromstring("<p>Simple text</p>")
        text = pmc_fetcher._extract_text(elem)
        assert text == "Simple text"

        # Element with nested tags
        elem = ElementTree.fromstring("<p>Text with <italic>italic</italic> and <bold>bold</bold></p>")
        text = pmc_fetcher._extract_text(elem)
        assert "italic" in text
        assert "bold" in text

        # None element
        text = pmc_fetcher._extract_text(None)
        assert text == ""

    def test_parse_pmc_xml_valid(self, pmc_fetcher):
        """Test parsing valid PMC XML response."""
        xml_response = """<?xml version="1.0" ?>
        <pmc-articleset>
            <article>
                <front>
                    <article-meta>
                        <article-id pub-id-type="pmc">12345678</article-id>
                        <article-id pub-id-type="pmid">87654321</article-id>
                        <article-id pub-id-type="doi">10.1234/test</article-id>
                        <title-group>
                            <article-title>Test Article Title</article-title>
                        </title-group>
                        <contrib-group>
                            <contrib contrib-type="author">
                                <name>
                                    <surname>Smith</surname>
                                    <given-names>John</given-names>
                                </name>
                            </contrib>
                        </contrib-group>
                        <pub-date pub-type="epub">
                            <year>2024</year>
                            <month>01</month>
                            <day>15</day>
                        </pub-date>
                        <abstract>
                            <p>This is the abstract text.</p>
                        </abstract>
                    </article-meta>
                    <journal-meta>
                        <journal-title>Test Journal</journal-title>
                    </journal-meta>
                </front>
                <body>
                    <sec sec-type="intro">
                        <title>Introduction</title>
                        <p>This is the introduction.</p>
                    </sec>
                    <sec sec-type="methods">
                        <title>Methods</title>
                        <p>These are the methods.</p>
                    </sec>
                    <sec sec-type="results">
                        <title>Results</title>
                        <p>These are the results.</p>
                    </sec>
                    <sec sec-type="discussion">
                        <title>Discussion</title>
                        <p>This is the discussion.</p>
                    </sec>
                </body>
                <back>
                    <ref-list>
                        <ref><mixed-citation>Reference 1</mixed-citation></ref>
                        <ref><mixed-citation>Reference 2</mixed-citation></ref>
                    </ref-list>
                </back>
            </article>
        </pmc-articleset>
        """

        article = pmc_fetcher._parse_pmc_xml(xml_response, "PMC12345678")

        assert article is not None
        assert article.pmc_id == "PMC12345678"
        assert article.title == "Test Article Title"
        assert "abstract" in article.abstract.lower()
        assert len(article.authors) == 1
        assert article.authors[0] == "Smith, John"
        assert article.journal == "Test Journal"
        assert "Introduction" in article.sections
        assert "Methods" in article.sections
        assert "Results" in article.sections
        assert "Discussion" in article.sections

    def test_parse_pmc_xml_with_recommendations(self, pmc_fetcher):
        """Test parsing PMC XML with recommendations and evidence grades."""
        xml_response = """<?xml version="1.0" ?>
        <pmc-articleset>
            <article>
                <front>
                    <article-meta>
                        <title-group>
                            <article-title>Clinical Guidelines</article-title>
                        </title-group>
                        <pub-date pub-type="epub">
                            <year>2024</year>
                        </pub-date>
                        <abstract><p>Guidelines abstract.</p></abstract>
                    </article-meta>
                    <journal-meta>
                        <journal-title>Guidelines Journal</journal-title>
                    </journal-meta>
                </front>
                <body>
                    <sec sec-type="recommendations">
                        <title>Recommendations</title>
                        <list list-type="order">
                            <list-item><p>1. First recommendation (Grade A)</p></list-item>
                            <list-item><p>2. Second recommendation (Grade B)</p></list-item>
                            <list-item><p>3. Third recommendation (Evidence C)</p></list-item>
                        </list>
                    </sec>
                </body>
            </article>
        </pmc-articleset>
        """

        article = pmc_fetcher._parse_pmc_xml(xml_response, "PMC99999")

        assert article is not None
        assert len(article.recommendations) >= 3
        assert any("Grade A" in rec or article.evidence_grades.get(rec) == "A"
                   for rec in article.recommendations)

    def test_parse_pmc_xml_empty(self, pmc_fetcher):
        """Test parsing empty PMC XML response."""
        xml_response = """<?xml version="1.0" ?>
        <pmc-articleset>
        </pmc-articleset>
        """

        article = pmc_fetcher._parse_pmc_xml(xml_response, "PMC99999")
        assert article is None

    def test_parse_pmc_xml_malformed(self, pmc_fetcher):
        """Test handling malformed XML gracefully."""
        xml_response = "not valid xml <>"

        article = pmc_fetcher._parse_pmc_xml(xml_response, "PMC99999")
        assert article is None

    def test_generate_full_text_markdown(self, pmc_fetcher):
        """Test markdown generation for full-text article."""
        article = FullTextArticle(
            pmc_id="PMC12345678",
            title="Test Clinical Guideline",
            abstract="This is a test abstract.",
            authors=["Smith, John", "Doe, Jane"],
            publication_date=datetime(2024, 1, 15),
            journal="Diabetes Care",
            sections={
                "Introduction": "This is the introduction.",
                "Methods": "These are the methods."
            },
            recommendations=[
                "1. First recommendation"
            ],
            evidence_grades={
                "1. First recommendation": "A"
            },
            article_type="clinical_guideline",
            confidence=1.0
        )

        markdown = pmc_fetcher.generate_full_text_markdown(article)

        # Check metadata header
        assert "source: PMC" in markdown
        assert "type: clinical_guideline" in markdown
        assert "confidence: 1.0" in markdown
        assert "pmc_id: PMC12345678" in markdown

        # Check title and content
        assert "# Test Clinical Guideline" in markdown
        assert "## Abstract" in markdown
        assert "## Introduction" in markdown
        assert "## Methods" in markdown

        # Check recommendations
        assert "## Key Recommendations" in markdown
        assert "First recommendation" in markdown
        assert "Grade A" in markdown

        # Check evidence grade summary
        assert "Evidence Grade Summary" in markdown


class TestPMCKnowledgeBaseIntegration:
    """Tests for PMC-related KnowledgeBaseIntegration methods."""

    def test_is_pmc_processed_empty(self, temp_storage):
        """Test PMC processed check with empty cache."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                "storage": {
                    "research_papers_dir": str(temp_storage / "docs" / "research-papers"),
                    "clinical_guidelines_dir": str(temp_storage / "docs" / "clinical-guidelines"),
                    "cache_dir": str(temp_storage / "data" / "cache"),
                    "processed_pmids_file": str(temp_storage / "data" / "cache" / "pubmed_processed.json"),
                    "processed_pmc_file": str(temp_storage / "data" / "cache" / "pmc_processed.json"),
                    "index_file": str(temp_storage / "docs" / "research-papers" / "index.json")
                },
                "api": {},
                "filters": {},
                "safety": {}
            }
            json.dump(config_data, f)
            config_path = f.name

        config = Config(Path(config_path))
        kb = KnowledgeBaseIntegration(config)

        assert kb.is_pmc_processed("PMC12345") is False

    def test_mark_pmc_processed(self, temp_storage):
        """Test marking PMC article as processed."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                "storage": {
                    "research_papers_dir": str(temp_storage / "docs" / "research-papers"),
                    "clinical_guidelines_dir": str(temp_storage / "docs" / "clinical-guidelines"),
                    "cache_dir": str(temp_storage / "data" / "cache"),
                    "processed_pmids_file": str(temp_storage / "data" / "cache" / "pubmed_processed.json"),
                    "processed_pmc_file": str(temp_storage / "data" / "cache" / "pmc_processed.json"),
                    "index_file": str(temp_storage / "docs" / "research-papers" / "index.json")
                },
                "api": {},
                "filters": {},
                "safety": {}
            }
            json.dump(config_data, f)
            config_path = f.name

        config = Config(Path(config_path))
        kb = KnowledgeBaseIntegration(config)

        # Initially not processed
        assert kb.is_pmc_processed("PMC12345") is False

        # Mark as processed
        kb.mark_pmc_processed("PMC12345")

        # Now should be processed
        assert kb.is_pmc_processed("PMC12345") is True


class TestIngestionStatsWithPMC:
    """Tests for IngestionStats with PMC fields."""

    def test_stats_includes_pmc_fields(self):
        """Test that stats include full-text fields."""
        stats = IngestionStats(
            search_term="diabetes",
            articles_found=100,
            articles_added=10,
            full_text_fetched=5,
            abstract_only=5
        )
        stats.end_time = datetime.now()

        data = stats.to_dict()

        assert 'full_text_fetched' in data
        assert data['full_text_fetched'] == 5
        assert 'abstract_only' in data
        assert data['abstract_only'] == 5


class TestConfigWithPMC:
    """Tests for Config with PMC settings."""

    def test_config_has_pmc_section(self, sample_config):
        """Test that config has PMC section."""
        pmc_config = sample_config.pmc_config
        assert pmc_config is not None

    def test_fetch_full_text_enabled_default(self, sample_config):
        """Test fetch_full_text_enabled defaults to False."""
        # Default should be False
        assert sample_config.fetch_full_text_enabled is False

    def test_config_storage_paths(self, sample_config):
        """Test storage paths for PMC content."""
        # These should return valid Path objects
        clinical_dir = sample_config.get_storage_path('clinical_guidelines_dir')
        assert clinical_dir is not None

        processed_pmc = sample_config.get_storage_path('processed_pmc_file')
        assert processed_pmc is not None
