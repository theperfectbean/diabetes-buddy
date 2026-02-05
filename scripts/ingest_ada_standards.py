#!/usr/bin/env python3
"""
ADA Standards of Care in Diabetes Ingestion Pipeline.

Fetches the American Diabetes Association Standards of Care from PubMed Central (PMC)
and ingests into ChromaDB for the Diabetes Buddy knowledge base.

Supports two ingestion modes:
1. Abstract-only: Automated PMC fetching (zero user action)
2. Full-text: User-provided PDFs for enhanced content

The ADA Standards are published annually as individual section articles in Diabetes Care.
This script:
1. Uses pre-verified PMC IDs for bulk fetching (faster, more reliable)
2. Fetches full-text XML from PMC for all sections
3. Parses content into logical sections with evidence levels
4. Chunks at section boundaries (~500-1000 tokens per chunk)
5. Ingests into ChromaDB with high-trust metadata
6. Detects and processes user-provided PDFs for enhanced content

Usage:
    python scripts/ingest_ada_standards.py [--year 2026] [--force]
    python scripts/ingest_ada_standards.py --pdf-only
    python scripts/ingest_ada_standards.py --validate-only
"""

import os
import re
import time
import argparse
import requests
from pathlib import Path
from datetime import datetime, timezone
from xml.etree import ElementTree
from typing import List, Dict, Optional, Tuple
import chromadb
from chromadb.config import Settings
import tiktoken
import PyPDF2

PROJECT_ROOT = Path(__file__).parent.parent
CHROMADB_PATH = PROJECT_ROOT / ".cache" / "chromadb"
DATA_PATH = PROJECT_ROOT / "data" / "knowledge" / "ada_standards"
PDF_DATA_PATH = PROJECT_ROOT / "data" / "knowledge" / "ada_standards_pdfs"

# Pre-verified PMC IDs for ADA Standards of Care 2026
# Volume 49, Supplement 1 (January 2026)
ADA_2026_PMC_IDS = {
    "intro": {"pmc_id": "12690168", "section": "0", "title": "Introduction and Methodology"},
    "summary": {"pmc_id": "12690167", "section": "0", "title": "Summary of Revisions"},
    "s1": {"pmc_id": "12690171", "section": "1", "title": "Improving Care and Promoting Health in Populations"},
    "s2": {"pmc_id": "12690183", "section": "2", "title": "Diagnosis and Classification of Diabetes"},
    "s3": {"pmc_id": "12690170", "section": "3", "title": "Prevention or Delay of Diabetes and Associated Comorbidities"},
    "s4": {"pmc_id": "12690184", "section": "4", "title": "Comprehensive Medical Evaluation and Assessment of Comorbidities"},
    "s5": {"pmc_id": "12690188", "section": "5", "title": "Facilitating Positive Health Behaviors and Well-being"},
    "s6": {"pmc_id": "12690178", "section": "6", "title": "Glycemic Goals, Hypoglycemia, and Hyperglycemic Crises"},
    "s7": {"pmc_id": "12690173", "section": "7", "title": "Diabetes Technology"},
    "s8": {"pmc_id": "12690172", "section": "8", "title": "Obesity and Weight Management"},
    "s9": {"pmc_id": "12690185", "section": "9", "title": "Pharmacologic Approaches to Glycemic Treatment"},
    "s10": {"pmc_id": "12690187", "section": "10", "title": "Cardiovascular Disease and Risk Management"},
    "s11": {"pmc_id": "12690176", "section": "11", "title": "Chronic Kidney Disease and Risk Management"},
    "s12": {"pmc_id": "12690177", "section": "12", "title": "Retinopathy, Neuropathy, and Foot Care"},
    "s13": {"pmc_id": "12690186", "section": "13", "title": "Older Adults"},
    "s14": {"pmc_id": "12690182", "section": "14", "title": "Children and Adolescents"},
    "s15": {"pmc_id": "12690181", "section": "15", "title": "Management of Diabetes in Pregnancy"},
    "s16": {"pmc_id": "12690180", "section": "16", "title": "Diabetes Care in the Hospital"},
    "s17": {"pmc_id": "12690165", "section": "17", "title": "Diabetes Advocacy"},
}

# ADA section topic mapping for enhanced metadata
SECTION_TOPICS = {
    "0": "Introduction and Methodology",
    "1": "Improving Care and Promoting Health in Populations",
    "2": "Diagnosis and Classification of Diabetes",
    "3": "Prevention or Delay of Diabetes and Associated Comorbidities",
    "4": "Comprehensive Medical Evaluation and Assessment of Comorbidities",
    "5": "Facilitating Positive Health Behaviors and Well-being",
    "6": "Glycemic Goals, Hypoglycemia, and Hyperglycemic Crises",
    "7": "Diabetes Technology",
    "8": "Obesity and Weight Management",
    "9": "Pharmacologic Approaches to Glycemic Treatment",
    "10": "Cardiovascular Disease and Risk Management",
    "11": "Chronic Kidney Disease and Risk Management",
    "12": "Retinopathy, Neuropathy, and Foot Care",
    "13": "Older Adults",
    "14": "Children and Adolescents",
    "15": "Management of Diabetes in Pregnancy",
    "16": "Diabetes Care in the Hospital",
    "17": "Diabetes Advocacy",
}

# Rate limiting: NCBI allows 3 requests/second without API key
REQUEST_DELAY = 0.4  # seconds between requests
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # exponential backoff multiplier


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """Chunk text into overlapping segments using tiktoken.

    Args:
        text: Text to chunk
        chunk_size: Target chunk size in tokens (500-1000 range for ADA content)
        overlap: Overlap between chunks in tokens

    Returns:
        List of text chunks
    """
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    start = 0

    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = enc.decode(chunk_tokens)

        # Only keep chunks with meaningful content
        if len(chunk_text.strip()) > 50:
            chunks.append(chunk_text)

        if end >= len(tokens):
            break
        start = max(0, end - overlap)

    return chunks


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text content from ADA Standards PDF.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted text content
    """
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            text_parts = []

            for page in reader.pages:
                page_text = page.extract_text()
                if page_text.strip():
                    text_parts.append(page_text)

            return "\n\n".join(text_parts)
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return ""


def parse_pdf_section_num(filename: str) -> Optional[str]:
    """Parse section number from PDF filename.

    Args:
        filename: PDF filename (e.g., "section_06_glycemic_goals.pdf")

    Returns:
        Section number string or None if not parseable
    """
    match = re.match(r'section_(\d+)_', filename)
    return match.group(1) if match else None


def ingest_ada_pdfs(year: int, collection_name: str = "ada_standards") -> Tuple[int, List[str]]:
    """Ingest user-provided ADA Standards PDFs into ChromaDB.

    Args:
        year: Publication year
        collection_name: ChromaDB collection name

    Returns:
        Tuple of (total_chunks_added, errors)
    """
    client = chromadb.PersistentClient(
        path=str(CHROMADB_PATH),
        settings=Settings(anonymized_telemetry=False)
    )

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine", "type": "clinical_guideline", "source_category": "clinical_guideline"}
    )

    pdf_dir = PDF_DATA_PATH
    if not pdf_dir.exists():
        return 0, []

    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        return 0, []

    print(f"\n📄 Detected {len(pdf_files)} ADA Standards PDFs")
    print(f"   Location: {pdf_dir}")

    total_chunks = 0
    errors = []

    for pdf_path in sorted(pdf_files):
        filename = pdf_path.name
        section_num = parse_pdf_section_num(filename)

        if not section_num:
            print(f"⚠️  Skipping {filename} - cannot parse section number")
            continue

        section_title = SECTION_TOPICS.get(section_num, f"Section {section_num}")

        print(f"\n[Section {section_num}] {section_title}")
        print(f"  Processing {filename}...")

        # Extract text from PDF
        content = extract_text_from_pdf(pdf_path)
        if not content:
            errors.append(f"Failed to extract text from {filename}")
            continue

        print(f"  ✓ Extracted {len(content):,} characters")

        # Parse into sub-sections (reuse existing logic)
        subsections = parse_section_boundaries(content, section_num)
        print(f"  Parsed into {len(subsections)} sub-sections")

        section_chunks = 0
        for subsection_name, subsection_content in subsections:
            chunks = chunk_text(subsection_content, chunk_size=800, overlap=100)

            for chunk_idx, chunk in enumerate(chunks):
                chunk_metadata = {
                    "source": "ADA_SOC_2026",
                    "document": f"Standards of Care in Diabetes-{year}",
                    "section": section_num,
                    "section_topic": section_title,
                    "subsection": subsection_name[:100],
                    "source_type": "full_text_pdf",
                    "year": year,
                    "confidence": 1.0,
                    "ingested_date": datetime.now(timezone.utc).isoformat(),
                    "filename": filename
                }

                # Create clean chunk ID with PDF indicator
                clean_subsection = re.sub(r'[^a-zA-Z0-9]', '_', subsection_name[:20])
                chunk_id = f"ada_pdf_{year}_s{section_num}_{clean_subsection}_{chunk_idx}"
                chunk_id = re.sub(r'_+', '_', chunk_id).strip('_')

                try:
                    collection.upsert(
                        ids=[chunk_id],
                        documents=[chunk],
                        metadatas=[chunk_metadata]
                    )
                    section_chunks += 1
                    total_chunks += 1
                except Exception as e:
                    errors.append(f"Section {section_num} chunk {chunk_idx}: {e}")

        print(f"  Ingested {section_chunks} chunks from PDF")

    return total_chunks, errors


def fetch_with_retry(url: str, params: Dict, max_retries: int = MAX_RETRIES) -> Optional[requests.Response]:
    """Fetch URL with exponential backoff retry logic.

    Args:
        url: URL to fetch
        params: Request parameters
        max_retries: Maximum number of retry attempts

    Returns:
        Response object or None if all retries failed
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            wait_time = REQUEST_DELAY * (RETRY_BACKOFF ** attempt)
            if attempt < max_retries - 1:
                print(f"    Retry {attempt + 1}/{max_retries} after {wait_time:.1f}s: {e}")
                time.sleep(wait_time)
            else:
                print(f"    Failed after {max_retries} attempts: {e}")
                return None
    return None


def fetch_pmc_full_text(pmc_id: str) -> Tuple[Optional[str], Dict]:
    """Fetch full-text XML from PMC with improved parsing.

    Args:
        pmc_id: PMC ID (e.g., "12690168" or "PMC12690168")

    Returns:
        Tuple of (full text content, metadata dict)
    """
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    fetch_url = f"{base_url}efetch.fcgi"

    # Remove PMC prefix if present
    pmc_num = pmc_id.replace("PMC", "")

    params = {
        "db": "pmc",
        "id": pmc_num,
        "rettype": "xml",
        "retmode": "xml"
    }

    response = fetch_with_retry(fetch_url, params)
    if response is None:
        return None, {}

    metadata = {}

    try:
        root = ElementTree.fromstring(response.content)
        text_parts = []

        # Check for publisher restriction on full-text XML
        # ADA and some publishers don't allow full-text XML download
        pmc_open_access = root.find(".//custom-meta[meta-name='pmc-prop-open-access']/meta-value")
        if pmc_open_access is not None and pmc_open_access.text == "no":
            metadata["full_text_restricted"] = True

        # Get article title
        title_elem = root.find(".//article-title")
        if title_elem is not None:
            title_text = "".join(title_elem.itertext()).strip()
            if title_text:
                text_parts.append(f"# {title_text}")
                metadata["title"] = title_text

        # Get abstract with all parts
        abstract = root.find(".//abstract")
        if abstract is not None:
            abstract_parts = []
            for elem in abstract.iter():
                if elem.tag == "title":
                    abstract_parts.append(f"\n### {elem.text or ''}")
                elif elem.tag == "p":
                    p_text = "".join(elem.itertext()).strip()
                    if p_text:
                        abstract_parts.append(p_text)
            if abstract_parts:
                text_parts.append("\n## Abstract")
                text_parts.extend(abstract_parts)

        # Get body sections with full content
        body = root.find(".//body")
        if body is not None:
            for sec in body.findall("sec"):
                sec_text = extract_section_text(sec, level=2)
                if sec_text.strip():
                    text_parts.append(sec_text)

        # Get back matter (if any recommendations there)
        back = root.find(".//back")
        if back is not None:
            for sec in back.findall(".//sec"):
                sec_text = extract_section_text(sec, level=2)
                if sec_text.strip() and len(sec_text) > 200:
                    text_parts.append(sec_text)

        if text_parts:
            content = "\n\n".join(text_parts)
            metadata["char_count"] = len(content)
            return content, metadata

    except Exception as e:
        print(f"    Error parsing PMC {pmc_id}: {e}")

    return None, {}


def extract_section_text(sec_elem, level: int = 2) -> str:
    """Recursively extract text from a section element.

    Args:
        sec_elem: XML section element
        level: Heading level for markdown formatting

    Returns:
        Formatted section text
    """
    parts = []
    heading_prefix = "#" * level

    # Get section title
    title = sec_elem.find("title")
    if title is not None:
        title_text = "".join(title.itertext()).strip()
        if title_text:
            parts.append(f"\n{heading_prefix} {title_text}")

    # Get direct paragraphs
    for child in sec_elem:
        if child.tag == "p":
            p_text = "".join(child.itertext()).strip()
            if p_text:
                parts.append(p_text)
        elif child.tag == "list":
            # Handle lists
            for item in child.findall(".//list-item"):
                item_text = "".join(item.itertext()).strip()
                if item_text:
                    parts.append(f"• {item_text}")
        elif child.tag == "sec":
            # Recurse into nested sections
            nested_text = extract_section_text(child, level=min(level + 1, 4))
            if nested_text.strip():
                parts.append(nested_text)
        elif child.tag == "boxed-text":
            # Handle boxed recommendations
            box_text = "".join(child.itertext()).strip()
            if box_text:
                parts.append(f"\n**Recommendation:**\n{box_text}")

    return "\n\n".join(parts)


def search_ada_standards(year: int = 2026, max_results: int = 30) -> List[str]:
    """Search PubMed for ADA Standards of Care articles.

    Args:
        year: Publication year to search for
        max_results: Maximum number of results to return

    Returns:
        List of PubMed IDs (PMIDs)
    """
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    search_url = f"{base_url}esearch.fcgi"

    # Search for Standards of Care in Diabetes articles
    query = f'Standards of Care in Diabetes-{year} Diabetes Care[journal]'

    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance"
    }

    response = fetch_with_retry(search_url, params)
    if response is None:
        return []

    try:
        data = response.json()
        pmids = data.get("esearchresult", {}).get("idlist", [])
        print(f"Found {len(pmids)} PMIDs for ADA Standards {year}")
        return pmids
    except Exception as e:
        print(f"Error parsing search results: {e}")
        return []


def get_pmc_ids(pmids: List[str]) -> Dict[str, str]:
    """Convert PubMed IDs to PMC IDs where available.

    Uses XML response from elink API since JSON mode can be unreliable.

    Args:
        pmids: List of PubMed IDs

    Returns:
        Dict mapping PMID to PMC ID (only for articles with PMC access)
    """
    if not pmids:
        return {}

    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    link_url = f"{base_url}elink.fcgi"

    # Use XML mode for more reliable parsing
    params = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "id": ",".join(pmids),
        "retmode": "xml"
    }

    response = fetch_with_retry(link_url, params)
    if response is None:
        return {}

    pmc_map = {}
    try:
        root = ElementTree.fromstring(response.content)

        # Parse LinkSet elements
        for linkset in root.findall(".//LinkSet"):
            # Get the source PMID
            id_elem = linkset.find(".//IdList/Id")
            if id_elem is None:
                continue
            pmid = id_elem.text

            # Look for PMC link
            for link_db in linkset.findall(".//LinkSetDb"):
                db_to = link_db.find("DbTo")
                if db_to is not None and db_to.text == "pmc":
                    pmc_id_elem = link_db.find(".//Link/Id")
                    if pmc_id_elem is not None:
                        pmc_map[pmid] = f"PMC{pmc_id_elem.text}"
                        break

    except Exception as e:
        print(f"Warning: Error parsing PMC links: {e}")

    print(f"Found {len(pmc_map)} articles with PMC full-text access")
    return pmc_map


def fetch_pubmed_abstracts(pmids: List[str]) -> List[Dict]:
    """Fetch article details and abstracts from PubMed.

    Args:
        pmids: List of PubMed IDs

    Returns:
        List of article dictionaries with title, abstract, section info
    """
    if not pmids:
        return []

    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    fetch_url = f"{base_url}efetch.fcgi"

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml"
    }

    response = fetch_with_retry(fetch_url, params)
    if response is None:
        return []

    articles = []
    try:
        root = ElementTree.fromstring(response.content)

        for article in root.findall(".//PubmedArticle"):
            try:
                # Extract PMID
                pmid_elem = article.find(".//PMID")
                pmid = pmid_elem.text if pmid_elem is not None else ""

                # Extract title
                title_elem = article.find(".//ArticleTitle")
                title = title_elem.text if title_elem is not None else ""

                # Skip non-Standards articles
                if "Standards of Care" not in title and "Standards of Medical Care" not in title:
                    continue

                # Extract section number from title (e.g., "9. Pharmacologic...")
                section_match = re.match(r'^(\d+)\.\s*(.+)', title)
                section_num = section_match.group(1) if section_match else None

                # Extract abstract - handle multiple AbstractText elements
                abstract_parts = []
                for abstract_text in article.findall(".//AbstractText"):
                    label = abstract_text.get("Label", "")
                    text = "".join(abstract_text.itertext()) or ""
                    if label and text:
                        abstract_parts.append(f"{label}: {text}")
                    elif text:
                        abstract_parts.append(text)
                abstract = " ".join(abstract_parts)

                # Extract publication date
                pub_date = None
                date_elem = article.find(".//PubDate")
                if date_elem is not None:
                    year_elem = date_elem.find("Year")
                    if year_elem is not None:
                        year_val = int(year_elem.text)
                        pub_date = datetime(year_val, 1, 1, tzinfo=timezone.utc)

                articles.append({
                    "pmid": pmid,
                    "title": title,
                    "abstract": abstract,
                    "section_num": section_num,
                    "section_topic": SECTION_TOPICS.get(section_num, "General"),
                    "pub_date": pub_date
                })

            except Exception as e:
                print(f"Error parsing article: {e}")
                continue

    except Exception as e:
        print(f"Error parsing PubMed response: {e}")

    return articles


def parse_section_boundaries(text: str, section_num: str) -> List[Tuple[str, str]]:
    """Parse text into logical sub-sections based on content structure.

    Args:
        text: Full section text
        section_num: ADA section number

    Returns:
        List of (subsection_name, content) tuples
    """
    sections = []

    # Split by major headings (## or ### patterns)
    heading_pattern = r'^(#{2,4})\s*(.+?)$'

    current_heading = f"Section {section_num} - Overview"
    current_content = []

    for line in text.split('\n'):
        # Check for heading
        heading_match = re.match(heading_pattern, line)
        if heading_match:
            # Save previous section
            if current_content:
                content = '\n'.join(current_content).strip()
                if len(content) > 100:  # Only keep meaningful sections
                    sections.append((current_heading, content))

            # Start new section
            current_heading = heading_match.group(2).strip()
            current_content = []
        else:
            current_content.append(line)

    # Save final section
    if current_content:
        content = '\n'.join(current_content).strip()
        if len(content) > 100:
            sections.append((current_heading, content))

    # If no sections found, return the whole text as one section
    if not sections:
        sections = [(f"Section {section_num}", text)]

    return sections


def ingest_from_pmc_bulk(year: int, force: bool = False) -> Tuple[int, List[str], int, int]:
    """Ingest ADA Standards directly from pre-verified PMC IDs.

    Args:
        year: Publication year (uses ADA_2026_PMC_IDS for 2026)
        force: If True, clear existing collection first

    Returns:
        Tuple of (total_chunks, errors, chunks_before, chunks_after)
    """
    if year != 2026:
        print(f"Bulk PMC fetch only available for 2026. Use --year 2026 or fallback to search mode.")
        return 0, ["Bulk fetch only supports 2026"], 0, 0

    client = chromadb.PersistentClient(
        path=str(CHROMADB_PATH),
        settings=Settings(anonymized_telemetry=False)
    )

    # Create or get collection
    if force:
        try:
            client.delete_collection(name="ada_standards")
            print("Cleared existing ada_standards collection")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name="ada_standards",
        metadata={"hnsw:space": "cosine", "type": "clinical_guideline", "source_category": "clinical_guideline"}
    )

    chunks_before = collection.count()
    total_chunks = 0
    errors = []
    successful_sections = []
    failed_sections = []

    print(f"\nFetching {len(ADA_2026_PMC_IDS)} sections from PMC...")

    for key, info in ADA_2026_PMC_IDS.items():
        pmc_id = info["pmc_id"]
        section_num = info["section"]
        section_title = info["title"]

        print(f"\n[Section {section_num}] {section_title}")
        print(f"  Fetching PMC{pmc_id}...")

        # Fetch full-text from PMC
        content, metadata = fetch_pmc_full_text(pmc_id)

        if not content:
            print(f"  ✗ Failed to retrieve content")
            failed_sections.append(f"Section {section_num}: {section_title}")
            errors.append(f"PMC{pmc_id}: No content retrieved")
            time.sleep(REQUEST_DELAY)
            continue

        # Check if full-text was restricted (abstract only)
        source_type = "full_text"
        if metadata.get("full_text_restricted"):
            source_type = "abstract"
            print(f"  ⚠ Publisher restricts full-text XML - using abstract only")

        print(f"  ✓ Retrieved {len(content):,} characters ({source_type})")
        successful_sections.append(f"Section {section_num}: {section_title}")

        # Parse into sub-sections
        subsections = parse_section_boundaries(content, section_num)
        print(f"  Parsed into {len(subsections)} sub-sections")

        section_chunks = 0
        for subsection_name, subsection_content in subsections:
            chunks = chunk_text(subsection_content, chunk_size=800, overlap=100)

            for chunk_idx, chunk in enumerate(chunks):
                chunk_metadata = {
                    "source": "ADA",
                    "document": f"Standards of Care in Diabetes-{year}",
                    "section": section_num,
                    "section_topic": SECTION_TOPICS.get(section_num, section_title),
                    "subsection": subsection_name[:100],
                    "pmc_id": f"PMC{pmc_id}",
                    "source_type": source_type,
                    "year": year,
                    "confidence": 1.0,
                    "ingested_date": datetime.now(timezone.utc).isoformat()
                }

                # Create clean chunk ID
                clean_subsection = re.sub(r'[^a-zA-Z0-9]', '_', subsection_name[:20])
                chunk_id = f"ada_{year}_s{section_num}_{clean_subsection}_{chunk_idx}"
                chunk_id = re.sub(r'_+', '_', chunk_id).strip('_')

                try:
                    collection.upsert(
                        ids=[chunk_id],
                        documents=[chunk],
                        metadatas=[chunk_metadata]
                    )
                    section_chunks += 1
                    total_chunks += 1
                except Exception as e:
                    errors.append(f"Section {section_num} chunk {chunk_idx}: {e}")

        print(f"  Ingested {section_chunks} chunks")

        # Rate limiting
        time.sleep(REQUEST_DELAY)

    print(f"\n{'='*60}")
    print("INGESTION SUMMARY")
    print(f"{'='*60}")
    print(f"Successful: {len(successful_sections)}/{len(ADA_2026_PMC_IDS)} sections")
    if failed_sections:
        print(f"Failed: {', '.join(failed_sections)}")

    return total_chunks, errors, chunks_before, collection.count()


def ingest_ada_standards(articles: List[Dict], pmc_map: Dict[str, str], year: int, force: bool = False):
    """Ingest ADA Standards articles into ChromaDB (fallback method).

    Args:
        articles: List of article dictionaries
        pmc_map: Mapping of PMID to PMC ID
        year: Publication year
        force: If True, clear existing collection first
    """
    client = chromadb.PersistentClient(
        path=str(CHROMADB_PATH),
        settings=Settings(anonymized_telemetry=False)
    )

    # Create or get collection
    if force:
        try:
            client.delete_collection(name="ada_standards")
            print("Cleared existing ada_standards collection")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name="ada_standards",
        metadata={"hnsw:space": "cosine", "type": "clinical_guideline", "source_category": "clinical_guideline"}
    )

    chunks_before = collection.count()
    total_chunks = 0
    errors = []

    for article in articles:
        pmid = article["pmid"]
        section_num = article["section_num"] or "0"

        print(f"Processing Section {section_num}: {article['section_topic']}...")

        # Try to get full-text from PMC first
        content = None
        source_type = "abstract"

        if pmid in pmc_map:
            print(f"  Fetching full-text from PMC ({pmc_map[pmid]})...")
            content, _ = fetch_pmc_full_text(pmc_map[pmid])
            if content:
                source_type = "full_text"
                print(f"  Retrieved {len(content):,} characters of full-text")
            time.sleep(REQUEST_DELAY)

        # Fall back to abstract if no full-text
        if not content:
            content = f"# {article['title']}\n\n{article['abstract']}"
            print(f"  Using abstract ({len(content)} characters)")

        # Parse into sub-sections
        subsections = parse_section_boundaries(content, section_num)

        # Chunk each sub-section
        for subsection_name, subsection_content in subsections:
            chunks = chunk_text(subsection_content, chunk_size=800, overlap=100)

            for chunk_idx, chunk in enumerate(chunks):
                metadata = {
                    "source": "ADA",
                    "document": f"Standards of Care in Diabetes-{year}",
                    "section": section_num,
                    "section_topic": article["section_topic"],
                    "subsection": subsection_name[:100],
                    "pmid": pmid,
                    "pmc_id": pmc_map.get(pmid, ""),
                    "source_type": source_type,
                    "year": year,
                    "confidence": 1.0,
                    "ingested_date": datetime.now(timezone.utc).isoformat()
                }

                chunk_id = f"ada_{year}_s{section_num}_{subsection_name[:20].replace(' ', '_')}_{chunk_idx}"
                chunk_id = re.sub(r'[^a-zA-Z0-9_]', '', chunk_id)

                try:
                    collection.upsert(
                        ids=[chunk_id],
                        documents=[chunk],
                        metadatas=[metadata]
                    )
                    total_chunks += 1
                except Exception as e:
                    errors.append(f"Section {section_num} chunk {chunk_idx}: {e}")

        time.sleep(REQUEST_DELAY)

    return total_chunks, errors, chunks_before, collection.count()


def validate_ingestion(year: int):
    """Run validation queries against the ingested collection.

    Args:
        year: Publication year to validate
    """
    client = chromadb.PersistentClient(
        path=str(CHROMADB_PATH),
        settings=Settings(anonymized_telemetry=False)
    )

    try:
        collection = client.get_collection(name="ada_standards")
    except Exception:
        print("Collection 'ada_standards' not found. Run ingestion first.")
        return

    # Test queries - should return high-confidence ADA results
    test_queries = [
        ("What is the HbA1c target for type 1 diabetes?", "6"),
        ("What are the blood pressure targets for diabetic patients?", "10"),
        ("How should hypoglycemia be treated?", "6"),
        ("What CGM recommendations does ADA provide?", "7"),
        ("Insulin management for type 1 diabetes", "9"),
    ]

    print("\n" + "=" * 60)
    print("VALIDATION QUERIES")
    print("=" * 60)

    for query, expected_section in test_queries:
        print(f"\nQuery: {query}")
        print(f"Expected: Section {expected_section}")

        start = time.time()
        results = collection.query(
            query_texts=[query],
            n_results=3
        )
        elapsed = (time.time() - start) * 1000

        if results['documents'] and results['documents'][0]:
            for i, (doc, meta, dist) in enumerate(zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            )):
                confidence = 1 - (dist / 2)
                snippet = doc[:120].replace('\n', ' ') + "..."
                section = meta.get('section', '?')
                match = "✓" if section == expected_section else ""
                print(f"  {i+1}. Section {section} ({meta.get('section_topic', 'Unknown')}) {match}")
                print(f"     {snippet}")
                print(f"     Confidence: {confidence:.3f} | Source: {meta.get('source_type', 'unknown')}")
        else:
            print("  No results found")

        print(f"  Query time: {elapsed:.0f}ms")


def main():
    parser = argparse.ArgumentParser(
        description="Ingest ADA Standards of Care into ChromaDB"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2026,
        help="Publication year (default: 2026)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clear existing collection before ingesting"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only run validation queries"
    )
    parser.add_argument(
        "--pdf-only",
        action="store_true",
        help="Only ingest user-provided PDFs (skip PMC fetching)"
    )
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="Use PubMed search fallback instead of bulk PMC fetch"
    )
    args = parser.parse_args()

    if args.validate_only:
        validate_ingestion(args.year)
        return

    # Handle PDF-only mode
    if args.pdf_only:
        print("=" * 60)
        print(f"ADA Standards PDF-Only Ingestion ({args.year})")
        print("=" * 60)

        pdf_chunks, pdf_errors = ingest_ada_pdfs(args.year)

        print("\n" + "=" * 60)
        print("=== PDF Ingestion Report ===")
        print("=" * 60)
        print(f"PDFs processed: {len(list(PDF_DATA_PATH.glob('*.pdf')))}")
        print(f"Chunks added: {pdf_chunks}")
        print(f"Errors: {len(pdf_errors)} {'- ' + '; '.join(pdf_errors[:3]) if pdf_errors else '[none]'}")

        if pdf_chunks > 0:
            print("\n[Validation] Running test queries...")
            validate_ingestion(args.year)

        print("\n" + "=" * 60)
        print("PDF ingestion complete!")
        print("=" * 60)
        return

    start_time = datetime.now(timezone.utc)
    print("=" * 60)
    print(f"ADA Standards of Care {args.year} Ingestion")
    print("=" * 60)
    print(f"Start: {start_time.isoformat()}")
    print(f"Mode: {'PubMed search (fallback)' if args.fallback else 'Bulk PMC fetch'}")

    # Ensure data directory exists
    DATA_PATH.mkdir(parents=True, exist_ok=True)

    if args.year == 2026 and not args.fallback:
        # Use bulk PMC fetch for 2026
        print("\n[Bulk PMC Fetch Mode]")
        total_chunks, errors, chunks_before, chunks_after = ingest_from_pmc_bulk(
            args.year, args.force
        )
        pmc_count = len(ADA_2026_PMC_IDS)
        sections_count = len(ADA_2026_PMC_IDS)
    else:
        # Fallback to PubMed search
        print("\n[Step 1] Searching PubMed for Standards of Care articles...")
        pmids = search_ada_standards(year=args.year)

        if not pmids:
            print("No articles found. Exiting.")
            return

        print("\n[Step 2] Checking PMC availability...")
        pmc_map = get_pmc_ids(pmids)

        print("\n[Step 3] Fetching article metadata from PubMed...")
        articles = fetch_pubmed_abstracts(pmids)
        print(f"Retrieved {len(articles)} Standards of Care sections")

        articles.sort(key=lambda x: int(x.get('section_num') or '99'))

        print("\n[Step 4] Ingesting into ChromaDB...")
        total_chunks, errors, chunks_before, chunks_after = ingest_ada_standards(
            articles, pmc_map, args.year, args.force
        )
        pmc_count = len(pmc_map)
        sections_count = len(articles)

        pmc_count = len(articles)

    # Check for and ingest user-provided PDFs
    print("\n[Step 5] Checking for user-provided PDFs...")
    pdf_chunks, pdf_errors = ingest_ada_pdfs(args.year)

    if pdf_chunks > 0:
        print(f"✓ Ingested {pdf_chunks} additional chunks from PDFs")
        chunks_after += pdf_chunks
        errors.extend(pdf_errors)
    else:
        print("ℹ️  No PDFs found in data/knowledge/ada_standards_pdfs/")
        print("   For enhanced content: run python scripts/download_ada_helper.py")

    # Print report
    end_time = datetime.now(timezone.utc)
    duration = end_time - start_time

    print("\n" + "=" * 60)
    print("=== ADA Standards of Care Ingestion Report ===")
    print("=" * 60)
    print(f"Year: {args.year}")
    print(f"Source: American Diabetes Association via PMC")
    print(f"\nArticles:")
    print(f"  - Sections processed: {sections_count}")
    print(f"  - Full-text sources: {pmc_count}")
    if pdf_chunks > 0:
        print(f"  - PDF enhancements: {pdf_chunks} chunks")
    print(f"\nChromaDB Collection: ada_standards")
    print(f"  - Chunks before: {chunks_before}")
    print(f"  - Chunks after: {chunks_after}")
    print(f"  - Chunks added: {chunks_after - chunks_before}")
    print(f"  - Confidence level: 1.0 (highest trust)")
    print(f"\nErrors: {len(errors)} {'- ' + '; '.join(errors[:3]) if errors else '[none]'}")
    print(f"\nDuration: {duration.seconds // 60}m {duration.seconds % 60}s")
    print(f"End: {end_time.isoformat()}")

    # Validate
    print("\n[Validation] Running test queries...")
    validate_ingestion(args.year)

    print("\n" + "=" * 60)
    print("Ingestion complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
