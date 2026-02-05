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
                    month_val = 1  # default
                    if month is not None:
                        month_text = month.text
                        # Handle both numeric and text month formats
                        month_names = {
                            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                        }
                        if month_text in month_names:
                            month_val = month_names[month_text]
                        elif month_text.isdigit():
                            month_val = int(month_text)
                    day_val = int(day.text) if day is not None and day.text.isdigit() else 1
                    try:
                        pub_date = datetime(year_val, month_val, day_val, tzinfo=timezone.utc)
                    except ValueError:
                        # Fallback to year only
                        pub_date = datetime(year_val, 1, 1, tzinfo=timezone.utc)

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
