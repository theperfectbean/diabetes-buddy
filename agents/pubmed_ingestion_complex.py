#!/usr/bin/env python3
"""
Simple PubMed Research Paper Ingestion for Diabetes Buddy Knowledge Base.

Fetches recent Type 1 Diabetes research papers from PubMed and ingests abstracts
into ChromaDB for the knowledge base.
"""

import os
import json
import time
import requests
import argparse
from pathlib import Path
from datetime import datetime, timezone
from xml.etree import ElementTree
import chromadb
from chromadb.config import Settings
import tiktoken

PROJECT_ROOT = Path(__file__).parent.parent
CHROMADB_PATH = PROJECT_ROOT / ".cache" / "chromadb"

def chunk_text(text, chunk_size=1000, overlap=100):
    """Chunk text into overlapping segments using tiktoken."""
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = enc.decode(chunk_tokens)
        chunks.append(chunk_text)
        if end >= len(tokens):
            break
        start = max(0, end - overlap)
    return chunks

def search_pubmed(query, max_results=30, mindate="2024", maxdate="2026"):
    """Search PubMed using E-utilities esearch."""
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    search_url = f"{base_url}esearch.fcgi"

    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "mindate": mindate,
        "maxdate": maxdate,
        "datetype": "pdat",
        "retmode": "json"
    }

    response = requests.get(search_url, params=params)
    response.raise_for_status()

    data = response.json()
    return data["esearchresult"]["idlist"]

def fetch_abstracts(pmids):
    """Fetch article details including abstracts using E-utilities efetch."""
    if not pmids:
        return []

    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    fetch_url = f"{base_url}efetch.fcgi"

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml"
    }

    response = requests.get(fetch_url, params=params)
    response.raise_for_status()

    root = ElementTree.fromstring(response.content)

    articles = []
    for article in root.findall(".//PubmedArticle"):
        try:
            # Extract PMID
            pmid_elem = article.find(".//PMID")
            pmid = pmid_elem.text if pmid_elem is not None else ""

            # Extract title
            title_elem = article.find(".//ArticleTitle")
            title = title_elem.text if title_elem is not None else ""

            # Extract abstract
            abstract_elem = article.find(".//AbstractText")
            abstract = abstract_elem.text if abstract_elem is not None else ""

            # Skip if no abstract
            if not abstract:
                continue

            # Extract authors
            authors = []
            for author in article.findall(".//Author"):
                last_name = author.find("LastName")
                fore_name = author.find("ForeName")
                if last_name is not None:
                    author_name = last_name.text
                    if fore_name is not None:
                        author_name += f", {fore_name.text}"
                    authors.append(author_name)

            # Extract publication date
            pub_date = None
            date_elem = article.find(".//PubDate")
            if date_elem is not None:
                year = date_elem.find("Year")
                month = date_elem.find("Month")
                day = date_elem.find("Day")
                if year is not None:
                    year_val = int(year.text)
                    month_val = int(month.text) if month is not None else 1
                    day_val = int(day.text) if day is not None else 1
                    pub_date = datetime(year_val, month_val, day_val, tzinfo=timezone.utc)

            articles.append({
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "pub_date": pub_date
            })

        except Exception as e:
            print(f"Error parsing article: {e}")
            continue

    return articles

def ingest_articles(articles):
    """Ingest articles into ChromaDB."""
    client = chromadb.PersistentClient(path=str(CHROMADB_PATH), settings=Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection(name="research_papers", metadata={"hnsw:space": "cosine", "type": "knowledge_base", "source_category": "knowledge_base"})

    chunks_before = collection.count()
    total_chunks = 0
    errors = []

    for article in articles:
        try:
            # Combine title and abstract
            content = f"{article['title']}\n\n{article['abstract']}"

            # Chunk the content
            chunks = chunk_text(content)

            # Prepare metadata
            pub_date_str = article['pub_date'].isoformat() if article['pub_date'] else ""
            authors_str = "; ".join(article['authors'][:3])  # Limit to first 3 authors

            # Prepare chunks for ingestion
            file_chunks = []
            for chunk_idx, chunk in enumerate(chunks):
                metadata = {
                    "source": "pubmed",
                    "pmid": article['pmid'],
                    "title": article['title'][:200],  # Truncate long titles
                    "authors": authors_str,
                    "pub_date": pub_date_str,
                    "confidence": 0.7,
                    "ingested_date": datetime.now(timezone.utc).isoformat()
                }
                file_chunks.append({
                    'id': f"pubmed_{article['pmid']}_{chunk_idx}",
                    'document': chunk,
                    'metadata': metadata
                })

            # Upsert in batches of 1 (conservative)
            for i in range(0, len(file_chunks), 1):
                batch = file_chunks[i:i+1]
                ids = [c['id'] for c in batch]
                documents = [c['document'] for c in batch]
                metadatas = [c['metadata'] for c in batch]

                retries = 3
                for attempt in range(retries):
                    try:
                        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
                        total_chunks += len(batch)
                        break
                    except Exception as e:
                        if attempt < retries - 1:
                            time.sleep(2 ** attempt)
                        else:
                            errors.append(f"Article {article['pmid']} batch {i}: {e}")

            print(f"Processed article {article['pmid']}: {len(chunks)} chunks")

            # Rate limiting: 1 second between articles
            time.sleep(1)

        except Exception as e:
            print(f"Error processing article {article['pmid']}: {e}")
            errors.append(f"Article {article['pmid']}: {e}")

    return total_chunks, errors, chunks_before, collection.count()

def main():
    parser = argparse.ArgumentParser(description="Ingest PubMed research papers into ChromaDB")
    parser.add_argument("--max-results", type=int, default=30, help="Maximum number of papers to fetch (default: 30)")
    args = parser.parse_args()

    start_time = datetime.now(timezone.utc)
    print(f"Starting PubMed ingestion: max_results={args.max_results}")

    # Search PubMed
    query = '"Type 1 Diabetes" AND ("insulin" OR "CGM" OR "closed loop")'
    print(f"Searching PubMed with query: {query}")

    pmids = search_pubmed(query, max_results=args.max_results)
    print(f"Found {len(pmids)} PMIDs")

    if not pmids:
        print("No articles found")
        return

    # Fetch abstracts
    print("Fetching article details...")
    articles = fetch_abstracts(pmids)
    print(f"Retrieved {len(articles)} articles with abstracts")

    # Ingest into ChromaDB
    print("Ingesting into ChromaDB...")
    total_chunks, errors, chunks_before, chunks_after = ingest_articles(articles)

    # Validation query
    client = chromadb.PersistentClient(path=str(CHROMADB_PATH), settings=Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection(name="research_papers", metadata={"hnsw:space": "cosine", "type": "knowledge_base", "source_category": "knowledge_base"})
    query_start = time.time()
    results = collection.query(query_texts=["What does recent research say about automated insulin delivery?"], n_results=3)
    query_time = (time.time() - query_start) * 1000

    # Print report
    end_time = datetime.now(timezone.utc)
    duration = end_time - start_time

    print("\n=== PubMed Research Paper Ingestion Report ===")
    print(f"Start: {start_time.isoformat()}")
    print(f"Query: {query}")
    print(f"Date range: 2024-2026")
    print(f"Max results: {args.max_results}")
    print(f"\nArticles Found: {len(pmids)}")
    print(f"Articles with Abstracts: {len(articles)}")
    print(f"\nChunking:")
    print(f"- Total chunks created: {total_chunks}")
    print(f"- Average chunks per article: {total_chunks/len(articles) if articles else 0:.1f}")
    print(f"\nChromaDB:")
    print(f"- Collection: research_papers")
    print(f"- Chunks before: {chunks_before}")
    print(f"- Chunks after: {chunks_after}")
    print(f"- Chunks added: {chunks_after - chunks_before}")
    print(f"\nValidation Query: \"What does recent research say about automated insulin delivery?\"")
    print("Top 3 Results:")
    if results['documents'] and results['documents'][0]:
        for j, (doc, meta, dist) in enumerate(zip(results['documents'][0], results['metadatas'][0], results['distances'][0])):
            snippet = doc[:100] + "..." if len(doc) > 100 else doc
            confidence = 1 - dist  # assuming cosine distance
            print(f"  {j+1}. {snippet} | PMID: {meta['pmid']} | confidence: {confidence:.3f}")
    else:
        print("  No results found")
    print(f"Query time: {query_time:.0f} ms")
    print(f"\nErrors: {errors if errors else '[none]'}")
    print(f"\nEnd: {end_time.isoformat()}")
    print(f"Duration: {duration.seconds // 60} minutes {duration.seconds % 60} seconds")

if __name__ == "__main__":
    main()
    "advocacy": "PMC12690183",
}

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Set up logging
_logs_dir = PROJECT_ROOT / "logs"
_logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(_logs_dir / 'pubmed_ingestion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class Author:
    """Represents an article author."""
    last_name: str
    fore_name: str = ""
    initials: str = ""
    affiliation: str = ""

    def __str__(self) -> str:
        if self.fore_name:
            return f"{self.last_name}, {self.fore_name}"
        return self.last_name


@dataclass
class Article:
    """Represents a PubMed article with extracted metadata."""
    pmid: str
    title: str
    abstract: str
    authors: list[Author]
    publication_date: datetime
    journal: str
    doi: Optional[str] = None
    pmc_id: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    language: str = "eng"
    is_open_access: bool = False
    relevance_score: float = 0.0
    requires_safety_review: bool = False
    confidence: float = 0.7

    def to_dict(self) -> dict:
        """Convert article to dictionary for JSON serialization."""
        data = asdict(self)
        data['authors'] = [str(a) for a in self.authors]
        data['publication_date'] = self.publication_date.isoformat()
        return data


@dataclass
class IngestionStats:
    """Statistics for an ingestion run."""
    search_term: str = ""
    articles_found: int = 0
    articles_filtered: int = 0
    articles_added: int = 0
    articles_skipped_duplicate: int = 0
    articles_skipped_relevance: int = 0
    articles_flagged_safety: int = 0
    full_text_fetched: int = 0
    abstract_only: int = 0
    errors: list[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert stats to dictionary."""
        return {
            'search_term': self.search_term,
            'articles_found': self.articles_found,
            'articles_filtered': self.articles_filtered,
            'articles_added': self.articles_added,
            'articles_skipped_duplicate': self.articles_skipped_duplicate,
            'articles_skipped_relevance': self.articles_skipped_relevance,
            'articles_flagged_safety': self.articles_flagged_safety,
            'full_text_fetched': self.full_text_fetched,
            'abstract_only': self.abstract_only,
            'errors': self.errors,
            'duration_seconds': (self.end_time - self.start_time).total_seconds() if self.end_time else 0
        }


@dataclass
class ArticleSection:
    """Represents a section of a full-text article."""
    title: str
    content: str
    level: int = 2  # H2, H3, etc.
    subsections: list['ArticleSection'] = field(default_factory=list)


@dataclass
class FullTextArticle:
    """Represents a full-text article from PMC."""
    pmc_id: str
    title: str
    abstract: str
    authors: list[str]
    publication_date: datetime
    journal: str
    sections: dict[str, str] = field(default_factory=dict)  # section_name -> content
    recommendations: list[str] = field(default_factory=list)
    evidence_grades: dict[str, str] = field(default_factory=dict)  # recommendation -> grade
    references: list[str] = field(default_factory=list)
    article_type: str = "research"  # "research" or "clinical_guideline"
    confidence: float = 0.7
    doi: Optional[str] = None
    pmid: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'pmc_id': self.pmc_id,
            'title': self.title,
            'abstract': self.abstract,
            'authors': self.authors,
            'publication_date': self.publication_date.isoformat(),
            'journal': self.journal,
            'sections': self.sections,
            'recommendations': self.recommendations,
            'evidence_grades': self.evidence_grades,
            'references': self.references,
            'article_type': self.article_type,
            'confidence': self.confidence,
            'doi': self.doi,
            'pmid': self.pmid
        }


# =============================================================================
# Configuration
# =============================================================================

class Config:
    """Configuration manager for PubMed ingestion."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to config file. Defaults to config/pubmed_config.json
        """
        self.config_path = config_path or PROJECT_ROOT / "config" / "pubmed_config.json"
        self._config: dict = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from JSON file."""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                self._config = json.load(f)
            logger.info(f"Loaded configuration from {self.config_path}")
        else:
            logger.warning(f"Config file not found at {self.config_path}, using defaults")
            self._config = self._get_defaults()

    def _get_defaults(self) -> dict:
        """Return default configuration."""
        return {
            "api": {
                "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
                "api_key_env": "PUBMED_API_KEY",
                "rate_limit_per_second": 3,
                "rate_limit_with_key": 10,
                "timeout_seconds": 30,
                "max_retries": 3,
                "retry_delay_seconds": 2
            },
            "search_terms": [
                "hybrid closed loop diabetes",
                "automated insulin delivery",
                "continuous glucose monitoring accuracy"
            ],
            "filters": {
                "days_back": 7,
                "max_results_per_query": 50,
                "language": "english",
                "require_abstract": True,
                "min_relevance_score": 0.6,
                "open_access_only": False
            },
            "safety": {
                "disclaimer": "Research summary. Consult healthcare provider.",
                "dosage_keywords": ["dosage", "dose", "units per"],
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
                    "ada_standards_2026": list(ADA_STANDARDS_2026_PMC_IDS.values())
                }
            }
        }

    @property
    def api_base_url(self) -> str:
        return self._config.get("api", {}).get("base_url", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/")

    @property
    def api_key(self) -> Optional[str]:
        env_var = self._config.get("api", {}).get("api_key_env", "PUBMED_API_KEY")
        return os.environ.get(env_var)

    @property
    def rate_limit(self) -> float:
        api_config = self._config.get("api", {})
        if self.api_key:
            return api_config.get("rate_limit_with_key", 10)
        return api_config.get("rate_limit_per_second", 3)

    @property
    def timeout(self) -> int:
        return self._config.get("api", {}).get("timeout_seconds", 30)

    @property
    def max_retries(self) -> int:
        return self._config.get("api", {}).get("max_retries", 3)

    @property
    def retry_delay(self) -> int:
        return self._config.get("api", {}).get("retry_delay_seconds", 2)

    @property
    def search_terms(self) -> list[str]:
        return self._config.get("search_terms", [])

    @property
    def filters(self) -> dict:
        return self._config.get("filters", {})

    @property
    def relevance_keywords(self) -> dict:
        return self._config.get("relevance_keywords", {})

    @property
    def safety_config(self) -> dict:
        return self._config.get("safety", {})

    @property
    def storage_config(self) -> dict:
        return self._config.get("storage", {})

    @property
    def pmc_config(self) -> dict:
        return self._config.get("pmc", {})

    @property
    def fetch_full_text_enabled(self) -> bool:
        return self.pmc_config.get("fetch_full_text", False)

    def get_storage_path(self, key: str) -> Path:
        """Get absolute path for a storage location."""
        relative_path = self.storage_config.get(key, "")
        return PROJECT_ROOT / relative_path


# =============================================================================
# PubMed API Client
# =============================================================================

class PubMedClient:
    """
    Async client for PubMed E-utilities API.

    Handles rate limiting, retries, and error handling for PubMed API requests.
    """

    def __init__(self, config: Config):
        """
        Initialize PubMed client.

        Args:
            config: Configuration object
        """
        self.config = config
        self.base_url = config.api_base_url
        self.api_key = config.api_key
        self._last_request_time = 0.0
        self._request_interval = 1.0 / config.rate_limit

    async def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        if elapsed < self._request_interval:
            await asyncio.sleep(self._request_interval - elapsed)
        self._last_request_time = time.time()

    async def _make_request(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        params: dict
    ) -> str:
        """
        Make a rate-limited request to PubMed API.

        Args:
            session: aiohttp session
            endpoint: API endpoint (e.g., 'esearch.fcgi')
            params: Query parameters

        Returns:
            Response text

        Raises:
            aiohttp.ClientError: On network errors after retries
        """
        await self._rate_limit()

        # Add API key if available
        if self.api_key:
            params['api_key'] = self.api_key

        url = f"{self.base_url}{endpoint}"

        for attempt in range(self.config.max_retries):
            try:
                logger.debug(f"Request to {endpoint}: {params}")
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as response:
                    response.raise_for_status()
                    return await response.text()
            except aiohttp.ClientError as e:
                logger.warning(f"Request attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    raise

        return ""  # Should not reach here

    async def search_articles(
        self,
        query: str,
        days_back: int = 7,
        max_results: int = 50
    ) -> list[str]:
        """
        Search PubMed for articles matching query.

        Args:
            query: Search query string
            days_back: Number of days to look back
            max_results: Maximum number of results to return

        Returns:
            List of PMIDs matching the query
        """
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        params = {
            'db': 'pubmed',
            'term': query,
            'retmax': max_results,
            'retmode': 'json',
            'datetype': 'pdat',
            'mindate': start_date.strftime('%Y/%m/%d'),
            'maxdate': end_date.strftime('%Y/%m/%d'),
            'sort': 'relevance'
        }

        logger.info(f"Searching PubMed for: {query} (last {days_back} days)")

        async with aiohttp.ClientSession() as session:
            try:
                response_text = await self._make_request(session, 'esearch.fcgi', params)
                data = json.loads(response_text)

                id_list = data.get('esearchresult', {}).get('idlist', [])
                count = data.get('esearchresult', {}).get('count', '0')
                logger.info(f"Found {count} articles, returning {len(id_list)} PMIDs")
                return id_list
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Error parsing search response: {e}")
                return []
            except aiohttp.ClientError as e:
                logger.error(f"Network error during search: {e}")
                return []

    async def fetch_article_details(self, pmid_list: list[str]) -> list[Article]:
        """
        Fetch detailed information for a list of PMIDs.

        Args:
            pmid_list: List of PubMed IDs

        Returns:
            List of Article objects with full metadata
        """
        if not pmid_list:
            return []

        params = {
            'db': 'pubmed',
            'id': ','.join(pmid_list),
            'retmode': 'xml',
            'rettype': 'abstract'
        }

        logger.info(f"Fetching details for {len(pmid_list)} articles")

        async with aiohttp.ClientSession() as session:
            try:
                response_text = await self._make_request(session, 'efetch.fcgi', params)
                return self._parse_article_xml(response_text)
            except aiohttp.ClientError as e:
                logger.error(f"Network error fetching details: {e}")
                return []

    def _parse_article_xml(self, xml_text: str) -> list[Article]:
        """
        Parse PubMed XML response into Article objects.

        Args:
            xml_text: XML response from efetch

        Returns:
            List of parsed Article objects
        """
        articles = []

        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as e:
            logger.error(f"XML parsing error: {e}")
            return articles

        for article_elem in root.findall('.//PubmedArticle'):
            try:
                article = self._parse_single_article(article_elem)
                if article:
                    articles.append(article)
            except Exception as e:
                logger.warning(f"Error parsing article: {e}")
                continue

        return articles

    def _parse_single_article(self, elem: ElementTree.Element) -> Optional[Article]:
        """Parse a single PubmedArticle element."""
        medline = elem.find('.//MedlineCitation')
        if medline is None:
            return None

        # Get PMID
        pmid_elem = medline.find('.//PMID')
        if pmid_elem is None or pmid_elem.text is None:
            return None
        pmid = pmid_elem.text

        # Get article data
        article_elem = medline.find('.//Article')
        if article_elem is None:
            return None

        # Title
        title_elem = article_elem.find('.//ArticleTitle')
        title = title_elem.text if title_elem is not None and title_elem.text else ""

        # Abstract
        abstract_parts = []
        for abstract_text in article_elem.findall('.//AbstractText'):
            label = abstract_text.get('Label', '')
            text = abstract_text.text or ''
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = ' '.join(abstract_parts)

        # Authors
        authors = []
        for author_elem in article_elem.findall('.//Author'):
            last_name = author_elem.findtext('LastName', '')
            fore_name = author_elem.findtext('ForeName', '')
            initials = author_elem.findtext('Initials', '')
            affiliation = author_elem.findtext('.//Affiliation', '')
            if last_name:
                authors.append(Author(
                    last_name=last_name,
                    fore_name=fore_name,
                    initials=initials,
                    affiliation=affiliation
                ))

        # Journal
        journal_elem = article_elem.find('.//Journal/Title')
        journal = journal_elem.text if journal_elem is not None and journal_elem.text else ""

        # Publication date
        pub_date = self._parse_pub_date(article_elem)

        # DOI
        doi = None
        for eloc in article_elem.findall('.//ELocationID'):
            if eloc.get('EIdType') == 'doi':
                doi = eloc.text
                break

        # PMC ID (indicates open access)
        pmc_id = None
        pmc_elem = elem.find('.//PubmedData/ArticleIdList/ArticleId[@IdType="pmc"]')
        if pmc_elem is not None:
            pmc_id = pmc_elem.text

        # Language
        lang_elem = article_elem.find('.//Language')
        language = lang_elem.text if lang_elem is not None and lang_elem.text else "eng"

        # Keywords
        keywords = []
        for kw_elem in medline.findall('.//KeywordList/Keyword'):
            if kw_elem.text:
                keywords.append(kw_elem.text)

        # MeSH terms
        mesh_terms = []
        for mesh_elem in medline.findall('.//MeshHeadingList/MeshHeading/DescriptorName'):
            if mesh_elem.text:
                mesh_terms.append(mesh_elem.text)

        return Article(
            pmid=pmid,
            title=title,
            abstract=abstract,
            authors=authors,
            publication_date=pub_date,
            journal=journal,
            doi=doi,
            pmc_id=pmc_id,
            keywords=keywords,
            mesh_terms=mesh_terms,
            language=language,
            is_open_access=pmc_id is not None
        )

    def _parse_pub_date(self, article_elem: ElementTree.Element) -> datetime:
        """Parse publication date from article element."""
        # Try PubDate first
        pub_date = article_elem.find('.//PubDate')
        if pub_date is not None:
            year = pub_date.findtext('Year', '')
            month = pub_date.findtext('Month', '1')
            day = pub_date.findtext('Day', '1')

            # Convert month name to number if needed
            if month.isalpha():
                month_names = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
                    'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
                    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                }
                month = str(month_names.get(month.lower()[:3], 1))

            try:
                return datetime(int(year), int(month), int(day))
            except (ValueError, TypeError):
                pass

        return datetime.now()

    def filter_open_access_only(self, articles: list[Article]) -> list[Article]:
        """
        Filter articles to only include open access articles.

        Args:
            articles: List of articles to filter

        Returns:
            List of open access articles (those with PMC IDs)
        """
        oa_articles = [a for a in articles if a.is_open_access]
        logger.info(f"Filtered to {len(oa_articles)} open access articles from {len(articles)} total")
        return oa_articles


# =============================================================================
# PMC Full-Text Fetcher
# =============================================================================

class PMCFullTextFetcher:
    """
    Fetches and parses full-text articles from PubMed Central (PMC).

    Reuses PubMedClient for API calls with rate limiting.
    """

    def __init__(self, client: PubMedClient, config: 'Config'):
        """
        Initialize PMC full-text fetcher.

        Args:
            client: PubMedClient instance for API calls
            config: Configuration object
        """
        self.client = client
        self.config = config
        self.base_url = config.api_base_url

    async def fetch_pmc_full_text(self, pmc_id: str) -> Optional[FullTextArticle]:
        """
        Fetch full-text article from PMC.

        Args:
            pmc_id: PMC ID (e.g., "PMC12690173" or "12690173")

        Returns:
            FullTextArticle object with parsed content, or None if not available
        """
        # Normalize PMC ID
        pmc_id_clean = pmc_id.replace("PMC", "").strip()
        pmc_id_full = f"PMC{pmc_id_clean}"

        logger.info(f"Fetching full-text from {pmc_id_full}...")

        params = {
            'db': 'pmc',
            'id': pmc_id_clean,
            'retmode': 'xml'
        }

        async with aiohttp.ClientSession() as session:
            try:
                response_text = await self.client._make_request(
                    session, 'efetch.fcgi', params
                )
                return self._parse_pmc_xml(response_text, pmc_id_full)
            except aiohttp.ClientError as e:
                logger.error(f"Network error fetching PMC {pmc_id_full}: {e}")
                return None
            except Exception as e:
                logger.error(f"Error fetching PMC {pmc_id_full}: {e}")
                return None

    def _parse_pmc_xml(self, xml_text: str, pmc_id: str) -> Optional[FullTextArticle]:
        """
        Parse PMC XML response into FullTextArticle.

        Args:
            xml_text: XML response from efetch
            pmc_id: PMC ID for the article

        Returns:
            Parsed FullTextArticle or None on error
        """
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as e:
            logger.error(f"XML parsing error for {pmc_id}: {e}")
            return None

        # Find the article element
        article_elem = root.find('.//article')
        if article_elem is None:
            # Try alternative structure
            article_elem = root.find('.//pmc-articleset/article')
            if article_elem is None:
                logger.warning(f"No article element found for {pmc_id}")
                return None

        # Extract front matter (metadata)
        front = article_elem.find('.//front')
        if front is None:
            logger.warning(f"No front matter found for {pmc_id}")
            return None

        # Title
        title = self._extract_text(front.find('.//article-title')) or ""

        # Abstract
        abstract_elem = front.find('.//abstract')
        abstract = self._extract_section_text(abstract_elem) if abstract_elem is not None else ""

        # Authors
        authors = self._extract_authors(front)

        # Publication date
        pub_date = self._extract_pmc_pub_date(front)

        # Journal
        journal = self._extract_text(front.find('.//journal-title')) or ""

        # DOI
        doi = None
        for article_id in front.findall('.//article-id'):
            if article_id.get('pub-id-type') == 'doi':
                doi = article_id.text

        # PMID
        pmid = None
        for article_id in front.findall('.//article-id'):
            if article_id.get('pub-id-type') == 'pmid':
                pmid = article_id.text

        # Extract body sections
        body = article_elem.find('.//body')
        sections = {}
        recommendations = []
        evidence_grades = {}

        if body is not None:
            sections, recommendations, evidence_grades = self._extract_body_sections(body)

        # Extract references
        references = self._extract_references(article_elem)

        # Determine article type based on content
        article_type = "research"
        is_ada_standard = pmc_id in ADA_STANDARDS_2026_PMC_IDS.values()
        if is_ada_standard or recommendations or evidence_grades:
            article_type = "clinical_guideline"

        # Set confidence based on article type
        confidence = 1.0 if article_type == "clinical_guideline" else 0.7

        return FullTextArticle(
            pmc_id=pmc_id,
            title=title,
            abstract=abstract,
            authors=authors,
            publication_date=pub_date,
            journal=journal,
            sections=sections,
            recommendations=recommendations,
            evidence_grades=evidence_grades,
            references=references,
            article_type=article_type,
            confidence=confidence,
            doi=doi,
            pmid=pmid
        )

    def _extract_text(self, elem: Optional[ElementTree.Element]) -> str:
        """Extract all text from an element, cleaning up XML artifacts."""
        if elem is None:
            return ""

        # Get all text content including from child elements
        text_parts = []

        def collect_text(e):
            if e.text:
                text_parts.append(e.text)
            for child in e:
                # Handle specific inline elements
                if child.tag in ('italic', 'bold', 'sup', 'sub'):
                    collect_text(child)
                elif child.tag == 'xref':
                    # Include reference text but mark it
                    if child.text:
                        text_parts.append(child.text)
                else:
                    collect_text(child)
                if child.tail:
                    text_parts.append(child.tail)

        collect_text(elem)
        return ' '.join(text_parts).strip()

    def _extract_section_text(self, elem: ElementTree.Element) -> str:
        """Extract text content from a section element."""
        paragraphs = []

        for p in elem.findall('.//p'):
            text = self._extract_text(p)
            if text:
                paragraphs.append(text)

        return '\n\n'.join(paragraphs)

    def _extract_authors(self, front: ElementTree.Element) -> list[str]:
        """Extract author names from front matter."""
        authors = []
        for contrib in front.findall('.//contrib[@contrib-type="author"]'):
            surname = self._extract_text(contrib.find('.//surname'))
            given_names = self._extract_text(contrib.find('.//given-names'))
            if surname:
                if given_names:
                    authors.append(f"{surname}, {given_names}")
                else:
                    authors.append(surname)
        return authors

    def _extract_pmc_pub_date(self, front: ElementTree.Element) -> datetime:
        """Extract publication date from PMC front matter."""
        # Try different date types
        for date_type in ['epub', 'ppub', 'pub']:
            pub_date = front.find(f'.//pub-date[@pub-type="{date_type}"]')
            if pub_date is not None:
                year = pub_date.findtext('year', '')
                month = pub_date.findtext('month', '1')
                day = pub_date.findtext('day', '1')

                try:
                    return datetime(int(year), int(month), int(day))
                except (ValueError, TypeError):
                    continue

        # Fallback to any pub-date
        pub_date = front.find('.//pub-date')
        if pub_date is not None:
            year = pub_date.findtext('year', str(datetime.now().year))
            try:
                return datetime(int(year), 1, 1)
            except (ValueError, TypeError):
                pass

        return datetime.now()

    def _extract_body_sections(
        self,
        body: ElementTree.Element
    ) -> tuple[dict[str, str], list[str], dict[str, str]]:
        """
        Extract sections, recommendations, and evidence grades from body.

        Args:
            body: Body element from PMC XML

        Returns:
            Tuple of (sections dict, recommendations list, evidence_grades dict)
        """
        sections = {}
        recommendations = []
        evidence_grades = {}

        # Standard section mappings
        section_mappings = {
            'intro': 'Introduction',
            'introduction': 'Introduction',
            'methods': 'Methods',
            'materials': 'Methods',
            'results': 'Results',
            'discussion': 'Discussion',
            'conclusions': 'Conclusions',
            'conclusion': 'Conclusions',
            'recommendations': 'Recommendations',
        }

        for sec in body.findall('.//sec'):
            sec_type = sec.get('sec-type', '').lower()
            title_elem = sec.find('title')
            title = self._extract_text(title_elem) if title_elem is not None else ""

            # Determine section name
            section_name = section_mappings.get(sec_type, title or "Other")

            # Extract section content
            content = self._extract_section_text(sec)

            if section_name and content:
                if section_name in sections:
                    sections[section_name] += '\n\n' + content
                else:
                    sections[section_name] = content

            # Extract recommendations from lists
            for list_elem in sec.findall('.//list'):
                list_type = list_elem.get('list-type', '')
                for item in list_elem.findall('.//list-item'):
                    item_text = self._extract_text(item)
                    if item_text:
                        # Check for numbered recommendations
                        if list_type == 'order' or re.match(r'^\d+\.', item_text):
                            recommendations.append(item_text)

                        # Check for evidence grades (A, B, C, E patterns)
                        grade_match = re.search(
                            r'\((?:Grade|Evidence)\s*([ABCE])\)',
                            item_text,
                            re.IGNORECASE
                        )
                        if grade_match:
                            evidence_grades[item_text] = grade_match.group(1).upper()

            # Also check for boxed text containing recommendations
            for boxed in sec.findall('.//boxed-text'):
                boxed_text = self._extract_section_text(boxed)
                if boxed_text:
                    # Parse for individual recommendations
                    rec_lines = boxed_text.split('\n')
                    for line in rec_lines:
                        line = line.strip()
                        if line and (re.match(r'^\d+\.', line) or line.startswith('•')):
                            recommendations.append(line)
                            grade_match = re.search(
                                r'\((?:Grade|Evidence)?\s*([ABCE])\)',
                                line,
                                re.IGNORECASE
                            )
                            if grade_match:
                                evidence_grades[line] = grade_match.group(1).upper()

        return sections, recommendations, evidence_grades

    def _extract_references(self, article_elem: ElementTree.Element) -> list[str]:
        """Extract references from the article."""
        references = []
        back = article_elem.find('.//back')
        if back is None:
            return references

        for ref in back.findall('.//ref'):
            ref_text = self._extract_text(ref)
            if ref_text:
                references.append(ref_text.strip())

        return references

    def generate_full_text_markdown(self, article: FullTextArticle) -> str:
        """
        Generate markdown output for a full-text article.

        Args:
            article: FullTextArticle to convert

        Returns:
            Markdown formatted string
        """
        disclaimer = self.config.safety_config.get(
            'disclaimer',
            "Research summary. Consult healthcare provider."
        )

        # Build metadata header
        md = f"""---
source: PMC
type: {article.article_type}
confidence: {article.confidence}
pmc_id: {article.pmc_id}
pmid: {article.pmid or 'N/A'}
doi: {article.doi or 'N/A'}
fetched_at: {datetime.now().isoformat()}
---

# {article.title}

> **Disclaimer:** {disclaimer}

## Metadata

| Field | Value |
|-------|-------|
| **PMC ID** | [{article.pmc_id}](https://www.ncbi.nlm.nih.gov/pmc/articles/{article.pmc_id}/) |
| **Authors** | {', '.join(article.authors[:3])}{'...' if len(article.authors) > 3 else ''} |
| **Journal** | {article.journal} |
| **Published** | {article.publication_date.strftime('%Y-%m-%d')} |
| **Article Type** | {article.article_type.replace('_', ' ').title()} |
| **Confidence** | {article.confidence} |

"""

        # Add abstract
        if article.abstract:
            md += f"""## Abstract

{article.abstract}

"""

        # Add sections in preferred order
        section_order = [
            'Introduction', 'Methods', 'Results', 'Discussion',
            'Conclusions', 'Recommendations'
        ]

        added_sections = set()
        for section_name in section_order:
            if section_name in article.sections:
                md += f"""## {section_name}

{article.sections[section_name]}

"""
                added_sections.add(section_name)

        # Add remaining sections
        for section_name, content in article.sections.items():
            if section_name not in added_sections:
                md += f"""## {section_name}

{content}

"""

        # Add recommendations with evidence grades
        if article.recommendations:
            md += "## Key Recommendations\n\n"
            for i, rec in enumerate(article.recommendations, 1):
                grade = article.evidence_grades.get(rec, '')
                grade_str = f" **(Grade {grade})**" if grade else ""
                md += f"{i}. {rec}{grade_str}\n"
            md += "\n"

        # Add evidence grades summary if present
        if article.evidence_grades:
            grade_counts = {}
            for grade in article.evidence_grades.values():
                grade_counts[grade] = grade_counts.get(grade, 0) + 1

            md += "### Evidence Grade Summary\n\n"
            md += "| Grade | Count | Meaning |\n"
            md += "|-------|-------|--------|\n"
            grade_meanings = {
                'A': 'Clear evidence from well-conducted RCTs',
                'B': 'Supportive evidence from well-conducted cohort studies',
                'C': 'Supportive evidence from poorly controlled studies',
                'E': 'Expert consensus or clinical experience'
            }
            for grade in sorted(grade_counts.keys()):
                meaning = grade_meanings.get(grade, 'Unknown')
                md += f"| {grade} | {grade_counts[grade]} | {meaning} |\n"
            md += "\n"

        # Add references (limited to first 10)
        if article.references:
            md += "## References\n\n"
            for i, ref in enumerate(article.references[:10], 1):
                md += f"{i}. {ref}\n"
            if len(article.references) > 10:
                md += f"\n*... and {len(article.references) - 10} more references*\n"
            md += "\n"

        md += f"""---
*Fetched from PubMed Central: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

        return md

    def generate_title_slug(self, title: str) -> str:
        """Generate a URL-friendly slug from title."""
        # Convert to lowercase and replace spaces with hyphens
        slug = title.lower()
        # Remove special characters
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        # Replace spaces with hyphens
        slug = re.sub(r'\s+', '-', slug)
        # Limit length
        slug = slug[:50].rstrip('-')
        return slug

    async def fetch_ada_standards(self) -> list[FullTextArticle]:
        """
        Fetch all ADA Standards 2026 sections from PMC.

        Returns:
            List of FullTextArticle objects for each standard section
        """
        articles = []
        total = len(ADA_STANDARDS_2026_PMC_IDS)

        logger.info(f"Fetching {total} ADA Standards 2026 sections from PMC...")

        for section_name, pmc_id in ADA_STANDARDS_2026_PMC_IDS.items():
            logger.info(f"Fetching ADA Standards section: {section_name} ({pmc_id})")

            article = await self.fetch_pmc_full_text(pmc_id)
            if article:
                # Mark as clinical guideline with highest confidence
                article.article_type = "clinical_guideline"
                article.confidence = 1.0
                articles.append(article)
                logger.info(f"Successfully fetched: {section_name}")
            else:
                logger.warning(f"Failed to fetch ADA Standards section: {section_name}")

        logger.info(f"Fetched {len(articles)}/{total} ADA Standards sections")
        return articles


# =============================================================================
# Article Processor
# =============================================================================

class ArticleProcessor:
    """
    Processes and filters articles for relevance and safety.
    """

    def __init__(self, config: Config):
        """
        Initialize article processor.

        Args:
            config: Configuration object
        """
        self.config = config
        self.filters = config.filters
        self.relevance_keywords = config.relevance_keywords
        self.safety_config = config.safety_config

    def filter_articles(self, articles: list[Article]) -> list[Article]:
        """
        Apply all filters to articles.

        Args:
            articles: List of articles to filter

        Returns:
            Filtered list of articles meeting all criteria
        """
        filtered = []

        for article in articles:
            # Check language
            if not self._check_language(article):
                logger.debug(f"Skipping {article.pmid}: non-English")
                continue

            # Check abstract
            if self.filters.get('require_abstract', True) and not article.abstract:
                logger.debug(f"Skipping {article.pmid}: no abstract")
                continue

            # Check publication date
            if not self._check_date(article):
                logger.debug(f"Skipping {article.pmid}: outside date range")
                continue

            # Calculate and check relevance score
            article.relevance_score = self._calculate_relevance(article)
            min_score = self.filters.get('min_relevance_score', 0.6)
            if article.relevance_score < min_score:
                logger.debug(f"Skipping {article.pmid}: low relevance ({article.relevance_score:.2f})")
                continue

            # Check for safety review requirements
            article.requires_safety_review = self._check_safety_flags(article)
            article.confidence = self.safety_config.get('default_confidence', 0.7)

            filtered.append(article)

        logger.info(f"Filtered to {len(filtered)} articles from {len(articles)} total")
        return filtered

    def _check_language(self, article: Article) -> bool:
        """Check if article is in allowed language."""
        allowed_lang = self.filters.get('language', 'english').lower()
        return article.language.lower() in ['eng', 'en', allowed_lang]

    def _check_date(self, article: Article) -> bool:
        """Check if article is within date range."""
        days_back = self.filters.get('days_back', 7)
        cutoff_date = datetime.now() - timedelta(days=days_back)
        return article.publication_date >= cutoff_date

    def _calculate_relevance(self, article: Article) -> float:
        """
        Calculate relevance score based on keyword matching.

        Args:
            article: Article to score

        Returns:
            Relevance score between 0.0 and 1.0
        """
        text = f"{article.title} {article.abstract}".lower()
        text += ' ' + ' '.join(article.keywords).lower()
        text += ' ' + ' '.join(article.mesh_terms).lower()

        score = 0.0
        max_score = 0.0

        # High weight keywords (0.3 each, max 3.0)
        high_keywords = self.relevance_keywords.get('high_weight', [])
        for kw in high_keywords:
            max_score += 0.3
            if kw.lower() in text:
                score += 0.3

        # Medium weight keywords (0.15 each)
        medium_keywords = self.relevance_keywords.get('medium_weight', [])
        for kw in medium_keywords:
            max_score += 0.15
            if kw.lower() in text:
                score += 0.15

        # Low weight keywords (0.05 each)
        low_keywords = self.relevance_keywords.get('low_weight', [])
        for kw in low_keywords:
            max_score += 0.05
            if kw.lower() in text:
                score += 0.05

        # Normalize to 0-1 range
        if max_score > 0:
            return min(score / max_score, 1.0)
        return 0.0

    def _check_safety_flags(self, article: Article) -> bool:
        """
        Check if article needs safety review (contains dosage info).

        Args:
            article: Article to check

        Returns:
            True if article should be flagged for safety review
        """
        text = f"{article.title} {article.abstract}".lower()

        dosage_keywords = self.safety_config.get('dosage_keywords', [])
        review_keywords = self.safety_config.get('flag_for_review_keywords', [])

        for kw in dosage_keywords + review_keywords:
            if kw.lower() in text:
                logger.info(f"Article {article.pmid} flagged for safety review: contains '{kw}'")
                return True

        return False

    def generate_structured_json(self, article: Article) -> dict:
        """
        Generate structured JSON for an article.

        Args:
            article: Article to convert

        Returns:
            Dictionary with article data and metadata
        """
        disclaimer = self.safety_config.get(
            'disclaimer',
            "Research summary. Consult healthcare provider."
        )

        return {
            'pmid': article.pmid,
            'title': article.title,
            'abstract': article.abstract,
            'authors': [str(a) for a in article.authors],
            'publication_date': article.publication_date.isoformat(),
            'journal': article.journal,
            'doi': article.doi,
            'pmc_id': article.pmc_id,
            'keywords': article.keywords,
            'mesh_terms': article.mesh_terms,
            'is_open_access': article.is_open_access,
            'relevance_score': article.relevance_score,
            'requires_safety_review': article.requires_safety_review,
            'confidence': article.confidence,
            'disclaimer': disclaimer,
            'ingested_at': datetime.now().isoformat(),
            'source': 'pubmed',
            'source_url': f"https://pubmed.ncbi.nlm.nih.gov/{article.pmid}/"
        }

    def generate_markdown_summary(self, article: Article) -> str:
        """
        Generate markdown summary for an article.

        Args:
            article: Article to summarize

        Returns:
            Markdown formatted summary
        """
        disclaimer = self.safety_config.get(
            'disclaimer',
            "Research summary. Consult healthcare provider."
        )

        # Format authors
        if len(article.authors) > 3:
            authors_str = f"{article.authors[0]}, et al."
        else:
            authors_str = ', '.join(str(a) for a in article.authors)

        # Build markdown
        md = f"""# {article.title}

> **Disclaimer:** {disclaimer}

## Metadata

| Field | Value |
|-------|-------|
| **PMID** | [{article.pmid}](https://pubmed.ncbi.nlm.nih.gov/{article.pmid}/) |
| **Authors** | {authors_str} |
| **Journal** | {article.journal} |
| **Published** | {article.publication_date.strftime('%Y-%m-%d')} |
| **DOI** | {article.doi or 'N/A'} |
| **Open Access** | {'Yes' if article.is_open_access else 'No'} |
| **Relevance Score** | {article.relevance_score:.2f} |
| **Confidence** | {article.confidence} |

"""

        if article.requires_safety_review:
            md += """
> **Safety Notice:** This article contains dosage or treatment recommendations.
> Flagged for Safety Auditor review before clinical application.

"""

        md += f"""## Abstract

{article.abstract}

"""

        if article.keywords:
            md += f"""## Keywords

{', '.join(article.keywords)}

"""

        if article.mesh_terms:
            md += f"""## MeSH Terms

{', '.join(article.mesh_terms)}

"""

        md += f"""---
*Ingested: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Source: PubMed*
"""

        return md


# =============================================================================
# Knowledge Base Integration
# =============================================================================

class KnowledgeBaseIntegration:
    """
    Integrates processed articles into the knowledge base.
    """

    def __init__(self, config: Config):
        """
        Initialize knowledge base integration.

        Args:
            config: Configuration object
        """
        self.config = config
        self.research_dir = config.get_storage_path('research_papers_dir')
        self.cache_dir = config.get_storage_path('cache_dir')
        self.processed_file = config.get_storage_path('processed_pmids_file')
        self.index_file = config.get_storage_path('index_file')

        # Ensure directories exist
        self.research_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Load processed PMIDs
        self._processed_pmids: set[str] = self._load_processed_pmids()

    def _load_processed_pmids(self) -> set[str]:
        """Load set of already processed PMIDs."""
        if self.processed_file.exists():
            try:
                with open(self.processed_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('processed_pmids', []))
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error loading processed PMIDs: {e}")
        return set()

    def _save_processed_pmids(self) -> None:
        """Save processed PMIDs to cache file."""
        data = {
            'processed_pmids': sorted(list(self._processed_pmids)),
            'last_updated': datetime.now().isoformat(),
            'count': len(self._processed_pmids)
        }
        with open(self.processed_file, 'w') as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Saved {len(self._processed_pmids)} processed PMIDs")

    def is_duplicate(self, pmid: str) -> bool:
        """
        Check if article has already been processed.

        Args:
            pmid: PubMed ID to check

        Returns:
            True if already processed
        """
        return pmid in self._processed_pmids

    def filter_duplicates(self, articles: list[Article]) -> tuple[list[Article], int]:
        """
        Filter out already processed articles.

        Args:
            articles: List of articles to filter

        Returns:
            Tuple of (new articles, count of duplicates skipped)
        """
        new_articles = []
        duplicates = 0

        for article in articles:
            if self.is_duplicate(article.pmid):
                logger.debug(f"Skipping duplicate: {article.pmid}")
                duplicates += 1
            else:
                new_articles.append(article)

        logger.info(f"Filtered {duplicates} duplicates, {len(new_articles)} new articles")
        return new_articles, duplicates

    def save_article(
        self,
        article: Article,
        article_json: dict,
        article_md: str
    ) -> bool:
        """
        Save article to knowledge base.

        Args:
            article: Article object
            article_json: Structured JSON data
            article_md: Markdown summary

        Returns:
            True if saved successfully
        """
        # Create month directory
        month_dir = self.research_dir / article.publication_date.strftime('%Y-%m')
        month_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        json_path = month_dir / f"article-{article.pmid}.json"
        try:
            with open(json_path, 'w') as f:
                json.dump(article_json, f, indent=2)
            logger.debug(f"Saved JSON: {json_path}")
        except IOError as e:
            logger.error(f"Error saving JSON for {article.pmid}: {e}")
            return False

        # Save Markdown
        md_path = month_dir / f"article-{article.pmid}.md"
        try:
            with open(md_path, 'w') as f:
                f.write(article_md)
            logger.debug(f"Saved Markdown: {md_path}")
        except IOError as e:
            logger.error(f"Error saving Markdown for {article.pmid}: {e}")
            return False

        # Mark as processed
        self._processed_pmids.add(article.pmid)

        return True

    def update_index(self) -> None:
        """Update the master index file with all articles."""
        index = {
            'last_updated': datetime.now().isoformat(),
            'total_articles': 0,
            'articles_by_month': {},
            'articles': []
        }

        # Scan all article JSON files
        for json_file in sorted(self.research_dir.glob('**/article-*.json')):
            try:
                with open(json_file, 'r') as f:
                    article_data = json.load(f)

                month = json_file.parent.name
                pmid = article_data.get('pmid', '')

                # Add to index
                index['articles'].append({
                    'pmid': pmid,
                    'title': article_data.get('title', ''),
                    'publication_date': article_data.get('publication_date', ''),
                    'relevance_score': article_data.get('relevance_score', 0),
                    'requires_safety_review': article_data.get('requires_safety_review', False),
                    'json_path': str(json_file.relative_to(self.research_dir)),
                    'md_path': str(json_file.with_suffix('.md').relative_to(self.research_dir))
                })

                # Count by month
                if month not in index['articles_by_month']:
                    index['articles_by_month'][month] = 0
                index['articles_by_month'][month] += 1
                index['total_articles'] += 1

            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error reading {json_file}: {e}")
                continue

        # Sort articles by date (newest first)
        index['articles'].sort(key=lambda x: x['publication_date'], reverse=True)

        # Save index
        try:
            with open(self.index_file, 'w') as f:
                json.dump(index, f, indent=2)
            logger.info(f"Updated index with {index['total_articles']} articles")
        except IOError as e:
            logger.error(f"Error saving index: {e}")

    def trigger_chromadb_reindex(self) -> bool:
        """
        Trigger ChromaDB re-indexing for new articles.

        Creates a dedicated 'pubmed_research' collection for PubMed articles.

        Returns:
            True if reindexing was successful
        """
        try:
            import chromadb
            from chromadb.config import Settings

            # Initialize ChromaDB client
            db_path = PROJECT_ROOT / ".cache" / "chromadb"
            db_path.mkdir(parents=True, exist_ok=True)

            client = chromadb.PersistentClient(
                path=str(db_path),
                settings=Settings(anonymized_telemetry=False)
            )

            # Get or create research papers collection
            # Use collection name from config or default
            collection_name = self.config.pmc_config.get('collection_name', 'pubmed_research')
            collection = client.get_or_create_collection(
                name="pubmed_research",
                metadata={"hnsw:space": "cosine", "type": "knowledge_base", "source_category": "knowledge_base"}
            )

            # Get existing document IDs to avoid duplicates
            existing_ids = set()
            if collection.count() > 0:
                result = collection.get()
                existing_ids = set(result['ids']) if result['ids'] else set()

            # Process all markdown files in research papers directory
            md_files = list(self.research_dir.glob('**/*.md'))
            logger.info(f"Found {len(md_files)} research paper documents")

            # Import LLM provider for embeddings
            try:
                from agents.llm_provider import LLMFactory
                llm = LLMFactory.get_provider()
            except ImportError:
                logger.warning("LLM provider not available, skipping embedding")
                return False

            added_count = 0
            for md_file in md_files:
                doc_id = md_file.stem

                # Skip if already indexed
                if doc_id in existing_ids:
                    logger.debug(f"Skipping already indexed: {doc_id}")
                    continue

                try:
                    with open(md_file, 'r') as f:
                        content = f.read()

                    # Chunk the content (similar to ChromaDBBackend)
                    chunks = self._chunk_text_for_indexing(content)

                    if not chunks:
                        continue

                    # Embed chunks
                    embeddings = llm.embed_text([c for c in chunks])

                    # Add to collection
                    chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
                    metadatas = [
                        {
                            'source': 'pubmed_research',
                            'source_name': 'PubMed Research Paper',
                            'document_id': doc_id,
                            'path': str(md_file),
                            'chunk_id': i,
                            'confidence': 0.7
                        }
                        for i in range(len(chunks))
                    ]

                    collection.add(
                        ids=chunk_ids,
                        embeddings=embeddings,
                        documents=chunks,
                        metadatas=metadatas
                    )

                    added_count += 1
                    logger.debug(f"Indexed: {doc_id} ({len(chunks)} chunks)")

                except Exception as e:
                    logger.warning(f"Error indexing {md_file}: {e}")
                    continue

            logger.info(f"ChromaDB reindexing complete: {added_count} new documents indexed")
            return True

        except ImportError as e:
            logger.warning(f"ChromaDB not available, skipping reindexing: {e}")
            return False
        except Exception as e:
            logger.error(f"Error during ChromaDB reindexing: {e}")
            return False

    def _chunk_text_for_indexing(
        self,
        text: str,
        chunk_size: int = 500,
        overlap: int = 100
    ) -> list[str]:
        """
        Chunk text into overlapping segments for vector indexing.

        Args:
            text: Text to chunk
            chunk_size: Words per chunk
            overlap: Overlapping words between chunks

        Returns:
            List of text chunks
        """
        words = text.split()
        chunks = []

        i = 0
        while i < len(words):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)

            # Only keep chunks with meaningful content
            if len(chunk_text.strip()) > 100:
                chunks.append(chunk_text)

            i += (chunk_size - overlap)

        return chunks

    def is_pmc_processed(self, pmc_id: str) -> bool:
        """
        Check if PMC article has already been processed.

        Args:
            pmc_id: PMC ID to check

        Returns:
            True if already processed
        """
        processed_pmc_file = self.config.get_storage_path('processed_pmc_file')
        if processed_pmc_file.exists():
            try:
                with open(processed_pmc_file, 'r') as f:
                    data = json.load(f)
                    return pmc_id in data.get('processed_pmc_ids', [])
            except (json.JSONDecodeError, IOError):
                pass
        return False

    def mark_pmc_processed(self, pmc_id: str) -> None:
        """Mark a PMC article as processed."""
        processed_pmc_file = self.config.get_storage_path('processed_pmc_file')
        processed_pmc_file.parent.mkdir(parents=True, exist_ok=True)

        data = {'processed_pmc_ids': [], 'last_updated': None}
        if processed_pmc_file.exists():
            try:
                with open(processed_pmc_file, 'r') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        if pmc_id not in data.get('processed_pmc_ids', []):
            data.setdefault('processed_pmc_ids', []).append(pmc_id)
            data['last_updated'] = datetime.now().isoformat()
            with open(processed_pmc_file, 'w') as f:
                json.dump(data, f, indent=2)

    def save_full_text_article(
        self,
        article: 'FullTextArticle',
        markdown_content: str,
        fetcher: 'PMCFullTextFetcher'
    ) -> bool:
        """
        Save a full-text PMC article to the knowledge base.

        Args:
            article: FullTextArticle object
            markdown_content: Pre-generated markdown content
            fetcher: PMCFullTextFetcher instance for generating slug

        Returns:
            True if saved successfully
        """
        # Determine output directory based on article type
        if article.article_type == "clinical_guideline":
            output_dir = self.config.get_storage_path('clinical_guidelines_dir')
        else:
            output_dir = self.research_dir / "pmc-full-text"

        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        title_slug = fetcher.generate_title_slug(article.title)
        filename = f"pmc-{article.pmc_id.replace('PMC', '')}-{title_slug}"

        # Save JSON
        json_path = output_dir / f"{filename}.json"
        try:
            with open(json_path, 'w') as f:
                json.dump(article.to_dict(), f, indent=2)
            logger.debug(f"Saved JSON: {json_path}")
        except IOError as e:
            logger.error(f"Error saving JSON for {article.pmc_id}: {e}")
            return False

        # Save Markdown
        md_path = output_dir / f"{filename}.md"
        try:
            with open(md_path, 'w') as f:
                f.write(markdown_content)
            logger.debug(f"Saved Markdown: {md_path}")
        except IOError as e:
            logger.error(f"Error saving Markdown for {article.pmc_id}: {e}")
            return False

        # Mark as processed
        self.mark_pmc_processed(article.pmc_id)

        return True

    def finalize(self) -> None:
        """Finalize the ingestion run (save caches, update index)."""
        self._save_processed_pmids()
        self.update_index()


# =============================================================================
# Main Ingestion Pipeline
# =============================================================================

class PubMedIngestionPipeline:
    """
    Main orchestrator for the PubMed ingestion pipeline.
    """

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the ingestion pipeline.

        Args:
            config: Configuration object. Creates default if not provided.
        """
        self.config = config or Config()
        self.client = PubMedClient(self.config)
        self.processor = ArticleProcessor(self.config)
        self.kb = KnowledgeBaseIntegration(self.config)
        self.stats: list[IngestionStats] = []

    async def run_search_term(
        self,
        search_term: str,
        days_back: int = 7,
        max_results: int = 50,
        open_access_only: bool = False,
        fetch_full_text: bool = False,
        pmc_fetcher: Optional['PMCFullTextFetcher'] = None
    ) -> IngestionStats:
        """
        Run ingestion for a single search term.

        Args:
            search_term: PubMed search query
            days_back: Days to look back
            max_results: Maximum results per query
            open_access_only: Only process open access articles
            fetch_full_text: Also fetch full-text from PMC
            pmc_fetcher: PMCFullTextFetcher instance (required if fetch_full_text)

        Returns:
            Statistics for this search
        """
        stats = IngestionStats(search_term=search_term)

        try:
            # Search for articles
            pmids = await self.client.search_articles(
                search_term,
                days_back=days_back,
                max_results=max_results
            )
            stats.articles_found = len(pmids)

            if not pmids:
                stats.end_time = datetime.now()
                return stats

            # Fetch article details
            articles = await self.client.fetch_article_details(pmids)

            # Filter to open access only if requested
            if open_access_only:
                articles = self.client.filter_open_access_only(articles)

            # Filter duplicates
            articles, duplicates = self.kb.filter_duplicates(articles)
            stats.articles_skipped_duplicate = duplicates

            # Filter by criteria
            filtered_articles = self.processor.filter_articles(articles)
            stats.articles_skipped_relevance = len(articles) - len(filtered_articles)
            stats.articles_filtered = len(filtered_articles)

            # Process and save each article
            for article in filtered_articles:
                article_json = self.processor.generate_structured_json(article)
                article_md = self.processor.generate_markdown_summary(article)

                if self.kb.save_article(article, article_json, article_md):
                    stats.articles_added += 1
                    if article.requires_safety_review:
                        stats.articles_flagged_safety += 1

                    # Attempt to fetch full-text if requested and article has PMC ID
                    if fetch_full_text and pmc_fetcher and article.pmc_id:
                        try:
                            if not self.kb.is_pmc_processed(article.pmc_id):
                                logger.info(f"Fetching full-text for {article.pmc_id}...")
                                full_text = await pmc_fetcher.fetch_pmc_full_text(article.pmc_id)
                                if full_text:
                                    ft_markdown = pmc_fetcher.generate_full_text_markdown(full_text)
                                    if self.kb.save_full_text_article(full_text, ft_markdown, pmc_fetcher):
                                        stats.full_text_fetched += 1
                                        logger.info(f"Saved full-text: {article.pmc_id}")
                                    else:
                                        stats.abstract_only += 1
                                else:
                                    stats.abstract_only += 1
                                    logger.debug(f"Full-text not available for {article.pmc_id}")
                            else:
                                logger.debug(f"Full-text already processed: {article.pmc_id}")
                                stats.full_text_fetched += 1
                        except Exception as e:
                            logger.warning(f"Error fetching full-text for {article.pmc_id}: {e}")
                            stats.abstract_only += 1
                    elif article.pmc_id:
                        stats.abstract_only += 1

        except Exception as e:
            logger.error(f"Error processing search term '{search_term}': {e}")
            stats.errors.append(str(e))

        stats.end_time = datetime.now()
        return stats

    async def run_full_ingestion(
        self,
        days_back: Optional[int] = None,
        max_results: Optional[int] = None,
        open_access_only: bool = False,
        fetch_full_text: bool = False
    ) -> list[IngestionStats]:
        """
        Run full ingestion for all configured search terms.

        Args:
            days_back: Override days to look back
            max_results: Override max results per query
            open_access_only: Only process open access articles
            fetch_full_text: Also fetch full-text from PMC for OA articles

        Returns:
            List of statistics for each search term
        """
        days = days_back or self.config.filters.get('days_back', 7)
        limit = max_results or self.config.filters.get('max_results_per_query', 50)

        # Check config for open_access_only if not set via CLI
        if not open_access_only:
            open_access_only = self.config.filters.get('open_access_only', False)

        logger.info(f"Starting full ingestion: {len(self.config.search_terms)} terms, "
                    f"{days} days back, max {limit} results each")
        if open_access_only:
            logger.info("Open access only mode enabled")
        if fetch_full_text:
            logger.info("Full-text fetching enabled for PMC articles")

        self.stats = []

        # Create PMC fetcher if needed
        pmc_fetcher = None
        if fetch_full_text:
            pmc_fetcher = PMCFullTextFetcher(self.client, self.config)

        for term in self.config.search_terms:
            stats = await self.run_search_term(
                term,
                days_back=days,
                max_results=limit,
                open_access_only=open_access_only,
                fetch_full_text=fetch_full_text,
                pmc_fetcher=pmc_fetcher
            )
            self.stats.append(stats)

            # Log progress
            logger.info(f"Term '{term}': found={stats.articles_found}, "
                        f"added={stats.articles_added}, skipped={stats.articles_skipped_duplicate}, "
                        f"full_text={stats.full_text_fetched}")

        # Finalize
        self.kb.finalize()

        # Trigger ChromaDB reindexing
        self.kb.trigger_chromadb_reindex()

        return self.stats

    def get_summary(self) -> dict:
        """Get summary of all ingestion runs."""
        total_found = sum(s.articles_found for s in self.stats)
        total_added = sum(s.articles_added for s in self.stats)
        total_skipped = sum(s.articles_skipped_duplicate for s in self.stats)
        total_filtered = sum(s.articles_skipped_relevance for s in self.stats)
        total_flagged = sum(s.articles_flagged_safety for s in self.stats)
        total_full_text = sum(s.full_text_fetched for s in self.stats)
        total_abstract_only = sum(s.abstract_only for s in self.stats)
        total_errors = sum(len(s.errors) for s in self.stats)

        return {
            'search_terms_processed': len(self.stats),
            'total_articles_found': total_found,
            'total_articles_added': total_added,
            'total_skipped_duplicates': total_skipped,
            'total_skipped_relevance': total_filtered,
            'total_flagged_safety': total_flagged,
            'total_full_text_fetched': total_full_text,
            'total_abstract_only': total_abstract_only,
            'total_errors': total_errors,
            'details': [s.to_dict() for s in self.stats]
        }

    def print_report(self) -> None:
        """Print a formatted report of the ingestion run."""
        summary = self.get_summary()

        print("\n" + "=" * 60)
        print("PubMed Ingestion Report")
        print("=" * 60)
        print(f"Search terms processed: {summary['search_terms_processed']}")
        print(f"Total articles found:   {summary['total_articles_found']}")
        print(f"Total articles added:   {summary['total_articles_added']}")
        print(f"Skipped (duplicates):   {summary['total_skipped_duplicates']}")
        print(f"Skipped (relevance):    {summary['total_skipped_relevance']}")
        print(f"Flagged for safety:     {summary['total_flagged_safety']}")

        # PMC full-text statistics
        if summary['total_full_text_fetched'] > 0 or summary['total_abstract_only'] > 0:
            print("-" * 60)
            print("PMC Full-Text Statistics:")
            print(f"  Full-text fetched:    {summary['total_full_text_fetched']}")
            print(f"  Abstract only:        {summary['total_abstract_only']}")

        print("-" * 60)
        print(f"Errors:                 {summary['total_errors']}")
        print("=" * 60)

        if summary['total_errors'] > 0:
            print("\nErrors encountered:")
            for stat in self.stats:
                for error in stat.errors:
                    print(f"  - [{stat.search_term}] {error}")


# =============================================================================
# CLI Interface
# =============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='PubMed Auto-Ingestion Pipeline for Diabetes Buddy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full ingestion with defaults (7 days, 50 results per term)
  python agents/pubmed_ingestion.py

  # Run with custom parameters
  python agents/pubmed_ingestion.py --days 14 --limit 100

  # Update index only (no new articles)
  python agents/pubmed_ingestion.py --update-index-only

  # Run with open access filter
  python agents/pubmed_ingestion.py --open-access-only

  # Fetch ADA Standards 2026 from PMC
  python agents/pubmed_ingestion.py --fetch-ada-standards

  # Fetch specific PMC article by ID
  python agents/pubmed_ingestion.py --fetch-pmc PMC12690173

  # Fetch full-text for open access articles
  python agents/pubmed_ingestion.py --open-access-only --fetch-full-text
        """
    )

    parser.add_argument(
        '--days', '-d',
        type=int,
        default=None,
        help='Number of days to look back (default: from config)'
    )

    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=None,
        help='Maximum results per search term (default: from config)'
    )

    parser.add_argument(
        '--update-index-only',
        action='store_true',
        help='Only update the index file, do not fetch new articles'
    )

    parser.add_argument(
        '--open-access-only',
        action='store_true',
        help='Only process open access articles with PMC IDs'
    )

    parser.add_argument(
        '--fetch-full-text',
        action='store_true',
        help='Fetch full-text from PMC for open access articles'
    )

    parser.add_argument(
        '--fetch-ada-standards',
        action='store_true',
        help='Fetch all ADA Standards 2026 sections from PMC'
    )

    parser.add_argument(
        '--fetch-pmc',
        type=str,
        default=None,
        metavar='PMC_ID',
        help='Fetch specific PMC article by ID (e.g., PMC12690173)'
    )

    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        help='Path to config file (default: config/pubmed_config.json)'
    )

    parser.add_argument(
        '--reindex',
        action='store_true',
        help='Trigger ChromaDB reindexing after ingestion'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    return parser.parse_args()


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load config
    config_path = Path(args.config) if args.config else None
    config = Config(config_path)

    # Handle update-index-only mode
    if args.update_index_only:
        logger.info("Running in update-index-only mode")
        kb = KnowledgeBaseIntegration(config)
        kb.update_index()

        if args.reindex:
            kb.trigger_chromadb_reindex()

        print("Index updated successfully")
        return 0

    # Handle --fetch-ada-standards
    if args.fetch_ada_standards:
        logger.info("Fetching ADA Standards 2026 from PMC...")
        client = PubMedClient(config)
        fetcher = PMCFullTextFetcher(client, config)
        kb = KnowledgeBaseIntegration(config)

        try:
            articles = await fetcher.fetch_ada_standards()

            saved_count = 0
            for article in articles:
                if kb.is_pmc_processed(article.pmc_id):
                    logger.info(f"Skipping already processed: {article.pmc_id}")
                    continue

                markdown = fetcher.generate_full_text_markdown(article)
                if kb.save_full_text_article(article, markdown, fetcher):
                    saved_count += 1
                    logger.info(f"Saved: {article.pmc_id} - {article.title[:50]}...")

            print("\n" + "=" * 60)
            print("ADA Standards 2026 Fetch Report")
            print("=" * 60)
            print(f"Total sections defined:  {len(ADA_STANDARDS_2026_PMC_IDS)}")
            print(f"Successfully fetched:    {len(articles)}")
            print(f"Saved to knowledge base: {saved_count}")
            print("=" * 60)

            if args.reindex:
                kb.trigger_chromadb_reindex()

            return 0 if len(articles) > 0 else 1

        except Exception as e:
            logger.error(f"Error fetching ADA Standards: {e}")
            return 1

    # Handle --fetch-pmc
    if args.fetch_pmc:
        pmc_id = args.fetch_pmc
        logger.info(f"Fetching PMC article: {pmc_id}")
        client = PubMedClient(config)
        fetcher = PMCFullTextFetcher(client, config)
        kb = KnowledgeBaseIntegration(config)

        try:
            article = await fetcher.fetch_pmc_full_text(pmc_id)

            if article is None:
                print(f"Failed to fetch article {pmc_id}")
                print("The article may not exist or full-text may not be available.")
                return 1

            if kb.is_pmc_processed(article.pmc_id):
                print(f"Article {pmc_id} has already been processed.")
                print("Use --reindex to update the ChromaDB index.")
                return 0

            markdown = fetcher.generate_full_text_markdown(article)
            if kb.save_full_text_article(article, markdown, fetcher):
                print("\n" + "=" * 60)
                print("PMC Article Fetch Report")
                print("=" * 60)
                print(f"PMC ID:       {article.pmc_id}")
                print(f"Title:        {article.title[:50]}...")
                print(f"Article Type: {article.article_type}")
                print(f"Confidence:   {article.confidence}")
                print(f"Sections:     {len(article.sections)}")
                print(f"Recommendations: {len(article.recommendations)}")
                print("=" * 60)

                if args.reindex:
                    kb.trigger_chromadb_reindex()

                return 0
            else:
                print(f"Failed to save article {pmc_id}")
                return 1

        except Exception as e:
            logger.error(f"Error fetching PMC article: {e}")
            return 1

    # Run full pipeline
    pipeline = PubMedIngestionPipeline(config)

    # Set options
    fetch_full_text = args.fetch_full_text or config.fetch_full_text_enabled

    try:
        await pipeline.run_full_ingestion(
            days_back=args.days,
            max_results=args.limit,
            open_access_only=args.open_access_only,
            fetch_full_text=fetch_full_text
        )
        pipeline.print_report()

        # Save summary to log
        summary = pipeline.get_summary()
        logger.info(f"Ingestion complete: {summary['total_articles_added']} articles added")

        return 0 if summary['total_errors'] == 0 else 1

    except KeyboardInterrupt:
        logger.info("Ingestion interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    exit(exit_code)
