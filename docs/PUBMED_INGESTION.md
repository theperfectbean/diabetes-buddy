# PubMed Auto-Ingestion Pipeline

Automated ingestion of diabetes research papers from PubMed into the Diabetes Buddy knowledge base, with support for PubMed Central (PMC) full-text retrieval.

## Overview

The pipeline:
1. Searches PubMed for recent articles using configured search terms
2. Filters by language, date, abstract availability, and relevance score
3. Flags articles with dosage recommendations for safety review
4. Saves structured JSON and markdown summaries
5. Optionally fetches full-text from PMC for open access articles
6. Indexes articles in ChromaDB for semantic search
7. Tracks processed articles to avoid duplicates

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run with defaults (7 days, 50 results per term)
python agents/pubmed_ingestion.py

# Custom parameters
python agents/pubmed_ingestion.py --days 14 --limit 100

# Update index only (no API calls)
python agents/pubmed_ingestion.py --update-index-only

# Fetch ADA Standards 2026 from PMC
python agents/pubmed_ingestion.py --fetch-ada-standards

# Fetch specific PMC article
python agents/pubmed_ingestion.py --fetch-pmc PMC12690173
```

## CLI Options

| Option | Description |
|--------|-------------|
| `--days, -d` | Days to look back (default: 7) |
| `--limit, -l` | Max results per search term (default: 50) |
| `--update-index-only` | Rebuild index without fetching new articles |
| `--open-access-only` | Only process articles with PMC IDs |
| `--fetch-full-text` | Fetch full-text from PMC for open access articles |
| `--fetch-ada-standards` | Fetch all ADA Standards 2026 sections from PMC |
| `--fetch-pmc PMC_ID` | Fetch specific PMC article by ID |
| `--reindex` | Trigger ChromaDB reindexing after ingestion |
| `--config, -c` | Path to config file |
| `--verbose, -v` | Enable debug logging |

## PMC Full-Text Retrieval

### Fetching ADA Standards 2026

The pipeline includes predefined PMC IDs for all 17 sections of the ADA Standards of Care 2026:

```bash
python agents/pubmed_ingestion.py --fetch-ada-standards
```

This fetches:
- Summary of Revisions
- Classification and Diagnosis
- Prevention or Delay of Diabetes
- Comprehensive Medical Evaluation
- Facilitating Positive Health Behaviors
- Glycemic Goals
- Diabetes Technology
- Obesity Management
- Pharmacologic Approaches
- Cardiovascular Disease
- Chronic Kidney Disease
- Retinopathy, Neuropathy, Foot Care
- Older Adults
- Children and Adolescents
- Management of Diabetes in Pregnancy
- Diabetes Care in the Hospital
- Advocacy for Diabetes Care

### Fetching Individual PMC Articles

```bash
# Fetch by PMC ID
python agents/pubmed_ingestion.py --fetch-pmc PMC12690173

# With reindexing
python agents/pubmed_ingestion.py --fetch-pmc PMC12690173 --reindex
```

### Full-Text with Regular Ingestion

```bash
# Fetch full-text for all open access articles found
python agents/pubmed_ingestion.py --open-access-only --fetch-full-text
```

### Full-Text Output Format

PMC full-text articles are saved to `docs/clinical-guidelines/ada-standards-2026/` with:

**Filename pattern:** `pmc-{id}-{title-slug}.md`

**YAML Frontmatter:**
```yaml
---
source: PMC
type: clinical_guideline
confidence: 1.0
pmc_id: PMC12690173
pmid: 12345678
doi: 10.2337/dc26-S007
fetched_at: 2026-01-20T10:30:00
---
```

**Content includes:**
- Abstract
- Full article sections (Introduction, Methods, Results, Discussion)
- Key recommendations with evidence grades
- Evidence grade summary table
- References (first 10)

## Configuration

Edit `config/pubmed_config.json`:

```json
{
  "api": {
    "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
    "api_key_env": "PUBMED_API_KEY",
    "rate_limit_per_second": 3,
    "rate_limit_with_key": 10
  },
  "search_terms": [
    "hybrid closed loop diabetes",
    "automated insulin delivery",
    ...
  ],
  "filters": {
    "days_back": 7,
    "max_results_per_query": 50,
    "language": "english",
    "require_abstract": true,
    "min_relevance_score": 0.6,
    "open_access_only": false
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
    "fetch_full_text": false,
    "clinical_guidelines": {
      "ada_standards_2026": ["PMC12690167", "PMC12690173", ...]
    }
  }
}
```

### PMC Configuration Options

| Option | Description |
|--------|-------------|
| `pmc.fetch_full_text` | Enable automatic full-text fetching (default: false) |
| `pmc.clinical_guidelines.ada_standards_2026` | List of PMC IDs for ADA Standards |

### API Key (Optional but Recommended)

Set `PUBMED_API_KEY` environment variable to increase rate limit from 3 to 10 requests/second:

```bash
export PUBMED_API_KEY="your_ncbi_api_key"
```

Get a free API key at: https://www.ncbi.nlm.nih.gov/account/settings/

## Search Terms

Default search terms focused on Type 1 diabetes management:

- `hybrid closed loop diabetes`
- `automated insulin delivery`
- `continuous glucose monitoring accuracy`
- `insulin pump therapy`
- `type 1 diabetes management`
- `dawn phenomenon treatment`
- `exercise blood glucose`
- `carbohydrate counting`
- `insulin sensitivity factor`

## Output Structure

### Directory Layout

```
docs/
├── research-papers/
│   ├── index.json                    # Master index of all articles
│   ├── 2024-01/
│   │   ├── article-12345678.json     # Structured data
│   │   └── article-12345678.md       # Markdown summary
│   └── pmc-full-text/                # Full-text research papers
│       └── pmc-12345678-article-title.md
├── clinical-guidelines/
│   └── ada-standards-2026/           # ADA clinical guidelines
│       ├── pmc-12690167-summary-of-revisions.json
│       ├── pmc-12690167-summary-of-revisions.md
│       └── ...
```

### JSON Format (Abstract-only)

```json
{
  "pmid": "12345678",
  "title": "Article Title",
  "abstract": "Full abstract text...",
  "authors": ["Smith, John", "Jones, Jane"],
  "publication_date": "2024-01-15T00:00:00",
  "journal": "Diabetes Care",
  "doi": "10.1234/dc.2024.12345",
  "pmc_id": "PMC9876543",
  "keywords": ["diabetes", "insulin pump"],
  "relevance_score": 0.85,
  "requires_safety_review": false,
  "confidence": 0.7,
  "disclaimer": "Research summary. Consult healthcare provider.",
  "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
}
```

### JSON Format (PMC Full-Text)

```json
{
  "pmc_id": "PMC12690173",
  "title": "7. Diabetes Technology: Standards of Care in Diabetes—2026",
  "abstract": "...",
  "authors": ["American Diabetes Association Professional Practice Committee"],
  "publication_date": "2025-12-20T00:00:00",
  "journal": "Diabetes Care",
  "sections": {
    "Introduction": "...",
    "Methods": "...",
    "Recommendations": "..."
  },
  "recommendations": [
    "7.1 Offer continuous glucose monitoring...(A)",
    "7.2 When prescribing CGM...(E)"
  ],
  "evidence_grades": {
    "7.1 Offer continuous glucose monitoring...(A)": "A",
    "7.2 When prescribing CGM...(E)": "E"
  },
  "references": ["..."],
  "article_type": "clinical_guideline",
  "confidence": 1.0,
  "doi": "10.2337/dc26-S007",
  "pmid": "12345678"
}
```

## Safety Features

### Confidence Levels

| Article Type | Confidence | Description |
|--------------|------------|-------------|
| Clinical Guidelines (ADA) | 1.0 | Official clinical guidelines |
| PMC Full-Text with Recommendations | 1.0 | Articles with evidence-graded recommendations |
| Research Papers | 0.7 | Standard research abstracts |
| Safety-Flagged Articles | 0.7 | Contains dosage information |

### Evidence Grades (ADA Standards)

| Grade | Meaning |
|-------|---------|
| A | Clear evidence from well-conducted RCTs |
| B | Supportive evidence from well-conducted cohort studies |
| C | Supportive evidence from poorly controlled studies |
| E | Expert consensus or clinical experience |

### Disclaimer

All article summaries include: *"Research summary for informational purposes only. Always consult your healthcare provider before making any changes to your diabetes management."*

### Safety Review Flags

Articles containing dosage-related content are automatically flagged:

- Keywords: `dosage`, `dose adjustment`, `units per`, `insulin dose`, etc.
- Flagged articles marked with `requires_safety_review: true`
- Default confidence set to 0.7 (lower than clinical guidelines)

## Relevance Scoring

Articles scored based on keyword presence:

| Weight | Keywords |
|--------|----------|
| High (0.3) | type 1 diabetes, insulin pump, cgm, closed loop, time in range |
| Medium (0.15) | diabetes mellitus, glucose monitoring, glycemic control, hba1c |
| Low (0.05) | diabetes, insulin, glucose |

Minimum score of 0.6 required for inclusion.

## Scheduled Execution

### Cron Setup

```bash
# Make script executable
chmod +x scripts/weekly_pubmed_update.sh

# Add to crontab (run every Monday at 4:00 AM)
crontab -e
0 4 * * 1 /path/to/diabetes-buddy/scripts/weekly_pubmed_update.sh
```

### Environment Variables for Cron

```bash
# Optional overrides
export PUBMED_API_KEY="your_key"
export PUBMED_DAYS_BACK=7
export PUBMED_MAX_RESULTS=50
export DIABETES_BUDDY_DIR="/path/to/project"
```

## ChromaDB Integration

Ingested articles are indexed in ChromaDB for semantic search:

```python
from agents.researcher_chromadb import ResearcherAgent

researcher = ResearcherAgent()
results = researcher.search_research_papers("hybrid closed loop efficacy")

for result in results:
    print(f"{result.quote[:200]}...")
    print(f"Confidence: {result.confidence:.2%}")
```

### Different Tagging in ChromaDB

| Article Type | Tags |
|--------------|------|
| Research papers | `type="research"`, `confidence=0.7` |
| Clinical guidelines | `type="clinical_guideline"`, `confidence=1.0` |

## Deduplication

### PubMed Articles
Processed PMIDs tracked in `data/cache/pubmed_processed.json`:

```json
{
  "processed_pmids": ["12345678", "87654321", ...],
  "last_updated": "2024-01-20T10:30:00",
  "count": 150
}
```

### PMC Full-Text Articles
Processed PMC IDs tracked in `data/cache/pmc_processed.json`:

```json
{
  "processed_pmc_ids": ["PMC12690167", "PMC12690173", ...],
  "last_updated": "2024-01-20T10:30:00"
}
```

Articles already in cache are skipped automatically.

## Logging

Logs written to `logs/pubmed_ingestion.log`:

```
2024-01-20 10:30:00 - pubmed_ingestion - INFO - Searching PubMed for: hybrid closed loop diabetes
2024-01-20 10:30:01 - pubmed_ingestion - INFO - Found 45 articles, returning 45 PMIDs
2024-01-20 10:30:05 - pubmed_ingestion - INFO - Filtered to 12 articles from 45 total
2024-01-20 10:30:06 - pubmed_ingestion - INFO - Article 12345678 flagged for safety review
2024-01-20 10:30:10 - pubmed_ingestion - INFO - Fetching full-text from PMC12690173...
2024-01-20 10:30:12 - pubmed_ingestion - INFO - Saved full-text: PMC12690173
```

### Ingestion Report

After each run, a summary report is printed:

```
============================================================
PubMed Ingestion Report
============================================================
Search terms processed: 9
Total articles found:   234
Total articles added:   45
Skipped (duplicates):   150
Skipped (relevance):    39
Flagged for safety:     8
------------------------------------------------------------
PMC Full-Text Statistics:
  Full-text fetched:    12
  Abstract only:        33
------------------------------------------------------------
Errors:                 0
============================================================
```

## Testing

```bash
# Run all tests
pytest tests/test_pubmed_ingestion.py -v

# Run specific test class
pytest tests/test_pubmed_ingestion.py::TestArticleProcessor -v
pytest tests/test_pubmed_ingestion.py::TestPMCFullTextFetcher -v

# Run with coverage
pytest tests/test_pubmed_ingestion.py --cov=agents.pubmed_ingestion
```

### Test Classes

| Class | Tests |
|-------|-------|
| `TestAuthor` | Author dataclass |
| `TestArticle` | Article dataclass |
| `TestConfig` | Configuration loading |
| `TestArticleProcessor` | Filtering and scoring |
| `TestKnowledgeBaseIntegration` | Storage and deduplication |
| `TestPubMedClient` | API client |
| `TestXMLParsing` | PubMed XML parsing |
| `TestPubMedIngestionPipeline` | Full pipeline |
| `TestADAStandardsConstants` | ADA PMC IDs |
| `TestFullTextArticle` | Full-text dataclass |
| `TestPMCFullTextFetcher` | PMC fetching and parsing |
| `TestPMCKnowledgeBaseIntegration` | PMC deduplication |
| `TestIngestionStatsWithPMC` | Statistics tracking |
| `TestConfigWithPMC` | PMC configuration |

## Troubleshooting

### Rate Limiting Errors

If you see 429 errors, the rate limit is being exceeded:
- Get an NCBI API key (free) to increase from 3 to 10 req/sec
- Reduce `--limit` parameter

### No Articles Found

- Check search terms match PubMed syntax
- Increase `--days` parameter
- Lower `min_relevance_score` in config

### PMC Full-Text Not Available

Not all PMC articles have full-text available via the API:
- Article may be embargoed
- Full-text may only be available on publisher site
- The pipeline gracefully falls back to abstract-only

### ChromaDB Indexing Fails

- Ensure `GOOGLE_API_KEY` or LLM provider is configured
- Check `.cache/chromadb/` directory permissions

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  PubMed API     │───▶│  PubMedClient    │───▶│ ArticleProcessor│
│  (E-utilities)  │    │  (rate-limited)  │    │ (filter/score)  │
└─────────────────┘    └──────────────────┘    └────────┬────────┘
                                                        │
┌─────────────────┐    ┌──────────────────┐    ┌────────▼────────┐
│  PMC API        │───▶│PMCFullTextFetcher│───▶│ KnowledgeBase   │
│  (full-text)    │    │  (XML parsing)   │    │ Integration     │
└─────────────────┘    └──────────────────┘    └────────┬────────┘
                                                        │
                       ┌──────────────────┐    ┌────────▼────────┐
                       │  ChromaDB        │◀───│ docs/           │
                       │  (embeddings)    │    │ (JSON + MD)     │
                       └──────────────────┘    └─────────────────┘
```

## Key Classes

| Class | Purpose |
|-------|---------|
| `PubMedClient` | API client with rate limiting |
| `PMCFullTextFetcher` | PMC full-text retrieval and XML parsing |
| `ArticleProcessor` | Filtering, scoring, and safety flagging |
| `KnowledgeBaseIntegration` | Storage and deduplication |
| `PubMedIngestionPipeline` | Main orchestrator |
| `Article` | PubMed article dataclass |
| `FullTextArticle` | PMC full-text article dataclass |
| `Config` | Configuration manager |
