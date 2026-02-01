#!/usr/bin/env python3
"""
Knowledge Base Status Checker for Diabetes Buddy

Displays current status of all knowledge sources including:
- ADA Standards (abstracts vs full-text PDFs)
- OpenAPS, Loop, AndroidAPS community docs
- PubMed research articles
- Wikipedia education content

Shows chunk counts, last update times, and recommendations.
"""

import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Tuple
import chromadb
from chromadb.config import Settings

PROJECT_ROOT = Path(__file__).parent.parent
CHROMADB_PATH = PROJECT_ROOT / ".cache" / "chromadb"
PDF_DATA_PATH = PROJECT_ROOT / "data" / "knowledge" / "ada_standards_pdfs"

# Knowledge source definitions
KNOWLEDGE_SOURCES = {
    "ada_standards": {
        "name": "ADA Standards 2026",
        "tier": 1,
        "description": "Clinical Guidelines",
        "collection": "ada_standards"
    },
    "openaps": {
        "name": "OpenAPS",
        "tier": 2,
        "description": "Community Documentation",
        "collection": "openaps_docs"
    },
    "androidaps": {
        "name": "AndroidAPS",
        "tier": 2,
        "description": "Community Documentation",
        "collection": "androidaps_docs"
    },
    "loop": {
        "name": "Loop",
        "tier": 2,
        "description": "Community Documentation",
        "collection": "loop_docs"
    },
    "pubmed": {
        "name": "PubMed Research",
        "tier": 3,
        "description": "Research",
        "collection": "pubmed_articles"
    },
    "wikipedia": {
        "name": "Wikipedia",
        "tier": 3,
        "description": "Education",
        "collection": "wikipedia"
    }
}

def get_collection_stats(collection_name: str) -> Tuple[int, str]:
    """Get chunk count and last update time for a collection.

    Args:
        collection_name: ChromaDB collection name

    Returns:
        Tuple of (chunk_count, last_update_iso)
    """
    try:
        client = chromadb.PersistentClient(
            path=str(CHROMADB_PATH),
            settings=Settings(anonymized_telemetry=False)
        )
        collection = client.get_collection(name=collection_name)

        count = collection.count()
        if count == 0:
            return 0, ""

        # Get most recent ingested_date from metadata
        results = collection.get(limit=1, include=["metadatas"])
        if results and results['metadatas']:
            last_update = results['metadatas'][0].get('ingested_date', '')
            return count, last_update

        return count, ""
    except Exception:
        return 0, ""

def check_ada_pdf_status() -> Tuple[int, bool]:
    """Check status of ADA Standards PDFs.

    Returns:
        Tuple of (pdf_count, has_uningested_pdfs)
    """
    if not PDF_DATA_PATH.exists():
        return 0, False

    pdf_files = list(PDF_DATA_PATH.glob("*.pdf"))
    pdf_count = len(pdf_files)

    # Check if PDFs are ingested by looking for PDF chunks in collection
    try:
        client = chromadb.PersistentClient(
            path=str(CHROMADB_PATH),
            settings=Settings(anonymized_telemetry=False)
        )
        collection = client.get_collection(name="ada_standards")

        # Count PDF-sourced chunks
        results = collection.get(include=["metadatas"])
        pdf_chunks = sum(1 for meta in results['metadatas']
                        if meta.get('source_type') == 'full_text_pdf')

        has_uningested = pdf_count > 0 and pdf_chunks == 0
        return pdf_count, has_uningested
    except Exception:
        return pdf_count, pdf_count > 0

def format_last_update(iso_string: str) -> str:
    """Format ISO datetime string for display.

    Args:
        iso_string: ISO format datetime string

    Returns:
        Formatted date string
    """
    if not iso_string:
        return "Unknown"

    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M AEST")
    except Exception:
        return "Unknown"

def main():
    print("🩺 Diabetes Buddy Knowledge Base Status")
    print("=" * 60)

    total_chunks = 0
    latest_update = ""
    tier_stats = {1: [], 2: [], 3: []}

    # Check ADA PDF status
    pdf_count, has_uningested_pdfs = check_ada_pdf_status()

    for source_key, source_info in KNOWLEDGE_SOURCES.items():
        chunk_count, last_update = get_collection_stats(source_info["collection"])

        if last_update and (not latest_update or last_update > latest_update):
            latest_update = last_update

        total_chunks += chunk_count
        tier_stats[source_info["tier"]].append((source_key, chunk_count, last_update))

    print(f"\n📊 Overall Status: {total_chunks} chunks across {len(KNOWLEDGE_SOURCES)} collections")
    print(f"   Last updated: {format_last_update(latest_update)}")
    print()

    # Tier 1: Clinical Guidelines
    print("🏥 Tier 1 - Clinical Guidelines:")
    ada_chunks, ada_update = get_collection_stats("ada_standards")
    ada_abstract_chunks = 0
    ada_pdf_chunks = 0

    try:
        client = chromadb.PersistentClient(
            path=str(CHROMADB_PATH),
            settings=Settings(anonymized_telemetry=False)
        )
        collection = client.get_collection(name="ada_standards")
        results = collection.get(include=["metadatas"])

        for meta in results['metadatas']:
            if meta.get('source_type') in ['abstract', 'full_text']:
                ada_abstract_chunks += 1
            elif meta.get('source_type') == 'full_text_pdf':
                ada_pdf_chunks += 1
    except Exception:
        pass

    status_icon = "✅" if ada_chunks > 0 else "❌"
    pdf_status = ""
    if pdf_count > 0:
        if has_uningested_pdfs:
            pdf_status = " ⚠️  Full-text available - run: python scripts/ingest_ada_standards.py"
        else:
            pdf_status = " ✅ Full-text ingested"
    elif ada_chunks > 0:
        pdf_status = " ⚠️  Full-text available - run: python scripts/download_ada_helper.py"

    print(f"  {status_icon} ADA Standards 2026: {ada_chunks} chunks ({ada_abstract_chunks} abstracts + {ada_pdf_chunks} PDF){pdf_status}")

    # Tier 2: Community Documentation
    print("\n📚 Tier 2 - Community Documentation:")
    for source_key, chunk_count, last_update in tier_stats[2]:
        source_info = KNOWLEDGE_SOURCES[source_key]
        status_icon = "✅" if chunk_count > 0 else "❌"
        print(f"  {status_icon} {source_info['name']}: {chunk_count} chunks")

    # Tier 3: Research & Education
    print("\n🔬 Tier 3 - Research & Education:")
    for source_key, chunk_count, last_update in tier_stats[3]:
        source_info = KNOWLEDGE_SOURCES[source_key]
        status_icon = "✅" if chunk_count > 0 else "❌"
        print(f"  {status_icon} {source_info['name']}: {chunk_count} chunks")

    print(f"\n📈 Total: {total_chunks} chunks across {len([s for s in KNOWLEDGE_SOURCES.values() if get_collection_stats(s['collection'])[0] > 0])} collections")

    # Recommendations
    recommendations = []

    if ada_chunks == 0:
        recommendations.append("Run: python scripts/ingest_ada_standards.py")

    if has_uningested_pdfs:
        recommendations.append("Run: python scripts/ingest_ada_standards.py (to ingest PDFs)")

    if pdf_count == 0 and ada_chunks > 0:
        recommendations.append("For enhanced ADA content: python scripts/download_ada_helper.py")

    missing_sources = [name for name, info in KNOWLEDGE_SOURCES.items()
                      if get_collection_stats(info['collection'])[0] == 0]
    if missing_sources:
        recommendations.append(f"Missing sources: {', '.join(missing_sources)}")

    if recommendations:
        print("\n💡 Recommendations:")
        for rec in recommendations:
            print(f"   • {rec}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()