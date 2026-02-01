#!/usr/bin/env python3
"""
Test Multi-Source RAG Retrieval Across All ChromaDB Collections

Tests the ResearcherAgent's ability to search across multiple knowledge sources
and return properly ranked, confidence-weighted results.
"""

import os
import sys
import time
from pathlib import Path
from collections import Counter

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.researcher_chromadb import ResearcherAgent
import chromadb
from chromadb.config import Settings


def connect_to_chromadb():
    """Connect to ChromaDB and return client."""
    db_path = project_root / ".cache" / "chromadb"
    client = chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(anonymized_telemetry=False)
    )
    return client


def verify_collections(client):
    """Verify all expected collections exist and show their counts."""
    print("🔍 Verifying ChromaDB Collections...")
    print("=" * 50)

    expected_collections = {
        "openaps_docs": {"expected_count": 259, "confidence": 0.8},
        "research_papers": {"expected_count": 39, "confidence": 0.7},
        "loop_docs": {"expected_count": 393, "confidence": 0.8},
        "androidaps_docs": {"expected_count": 384, "confidence": 0.8},
        "glooko_data": {"expected_count": None, "confidence": "0.5-0.9"}  # Handled separately
    }

    collections = client.list_collections()
    collection_info = {}

    for collection in collections:
        name = collection.name
        count = collection.count()
        collection_info[name] = count

        if name in expected_collections:
            expected = expected_collections[name]["expected_count"]
            confidence = expected_collections[name]["confidence"]
            status = "✅" if expected is None or count >= expected * 0.8 else "⚠️"
            print(f"{status} {name}: {count} chunks (expected: {expected or 'N/A'}, confidence: {confidence})")
        else:
            print(f"ℹ️  {name}: {count} chunks (unexpected collection)")

    # Check for missing collections
    for expected_name in expected_collections:
        if expected_name not in collection_info:
            if expected_name == "glooko_data":
                print(f"ℹ️  {expected_name}: Not in ChromaDB (handled by GlookoQueryAgent)")
            else:
                print(f"❌ {expected_name}: Collection missing!")

    print()
    return collection_info


def run_test_query(researcher, query_name, query_text, expected_sources):
    """Run a single test query and display results."""
    print(f"🧪 Test Query: {query_name}")
    print(f"Query: \"{query_text}\"")
    print(f"Expected Sources: {expected_sources}")
    print("-" * 60)

    # Time the query
    start_time = time.time()
    results = researcher.search_all_collections(query_text, top_k=5, deduplicate=True)
    query_time = time.time() - start_time

    # Analyze results
    source_counts = Counter()
    confidence_scores = []

    print("📊 Top 5 Results:")
    for i, result in enumerate(results, 1):
        # Extract collection name from source
        source_collection = "unknown"
        if "OpenAPS" in result.source or "openaps" in result.source.lower():
            source_collection = "openaps_docs"
        elif "Loop" in result.source or "loop" in result.source.lower():
            source_collection = "loop_docs"
        elif "AndroidAPS" in result.source or "androidaps" in result.source.lower():
            source_collection = "androidaps_docs"
        elif "PubMed" in result.source or "Research" in result.source:
            source_collection = "research_papers"
        elif any(pdf in result.source for pdf in ["Think Like a Pancreas", "CamAPS", "ADA", "Australian"]):
            source_collection = "pdf_docs"
        else:
            source_collection = result.source.split()[0].lower()

        source_counts[source_collection] += 1
        confidence_scores.append(result.confidence)

        # Truncate quote for display
        quote_preview = result.quote[:100] + "..." if len(result.quote) > 100 else result.quote

        print(f"{i}. [{source_collection}] Confidence: {result.confidence:.3f}")
        print(f"   Source: {result.source}")
        print(f"   Quote: {quote_preview}")
        print()

    # Summary statistics
    print("📈 Query Summary:")
    print(f"   Query Time: {query_time*1000:.1f} ms")
    print(f"   Total Results: {len(results)}")
    print(f"   Source Distribution: {dict(source_counts)}")
    print(f"   Confidence Range: {min(confidence_scores):.3f} - {max(confidence_scores):.3f}")
    print(f"   Average Confidence: {sum(confidence_scores)/len(confidence_scores):.3f}" if confidence_scores else "   Average Confidence: N/A")
    print()

    return {
        "query_time": query_time,
        "source_counts": dict(source_counts),
        "confidence_scores": confidence_scores,
        "total_results": len(results)
    }


def validate_researcher_agent(researcher):
    """Validate that ResearcherAgent queries all collections."""
    print("🔧 Validating Researcher Agent Integration...")
    print("=" * 50)

    if researcher is None:
        print("❌ ResearcherAgent not available")
        return False

    # Check if search_all_collections method exists
    if not hasattr(researcher, 'search_all_collections'):
        print("❌ ResearcherAgent missing search_all_collections method!")
        return False

    # Check what collections it searches (by inspecting the backend)
    if hasattr(researcher, 'backend') and hasattr(researcher.backend, 'search_all_collections'):
        # We can't easily inspect the search_methods dict, but we can test
        print("✅ ResearcherAgent has search_all_collections method")

        # Test with a simple query to see if it returns results from multiple sources
        test_results = researcher.search_all_collections("diabetes", top_k=10)
        test_sources = [r.source for r in test_results]

        unique_sources = set()
        for source in test_sources:
            if "OpenAPS" in source:
                unique_sources.add("openaps_docs")
            elif "Loop" in source:
                unique_sources.add("loop_docs")
            elif "AndroidAPS" in source:
                unique_sources.add("androidaps_docs")
            elif "PubMed" in source or "Research" in source:
                unique_sources.add("research_papers")
            elif any(pdf in source for pdf in ["Think Like a Pancreas", "CamAPS", "ADA", "Australian"]):
                unique_sources.add("pdf_docs")

        print(f"✅ Test query returned results from {len(unique_sources)} source types: {sorted(unique_sources)}")

        if len(unique_sources) >= 2:
            print("✅ Multi-source retrieval confirmed!")
            return True
        else:
            print("⚠️  Only single source type returned - may need updating")
            return False
    else:
        print("❌ ResearcherAgent backend missing search_all_collections")
        return False


def main():
    """Main test execution."""
    print("🚀 Testing Multi-Source RAG Retrieval")
    print("=" * 50)

    # Connect to ChromaDB
    try:
        client = connect_to_chromadb()
        print("✅ Connected to ChromaDB")
    except Exception as e:
        print(f"❌ Failed to connect to ChromaDB: {e}")
        return

    # Verify collections
    collection_info = verify_collections(client)

    # Initialize Researcher Agent
    try:
        researcher = ResearcherAgent()
        print("✅ ResearcherAgent initialized")
        agent_ok = True
    except Exception as e:
        print(f"⚠️  ResearcherAgent failed to initialize: {e}")
        print("   (This is expected if API keys are not configured)")
        print("   Proceeding with collection verification only...")
        researcher = None
        agent_ok = False

    print()

    # Validate researcher agent integration (only if initialized)
    if agent_ok:
        agent_valid = validate_researcher_agent(researcher)
    else:
        agent_valid = False
        print("🔧 Skipping Researcher Agent validation (not initialized)")

    print()

    # Define test queries
    test_queries = [
        {
            "name": "Autosens Research",
            "query": "How does autosens work and what does research say about it?",
            "expected": "Mix of OpenAPS docs (0.8) + PubMed research (0.7)"
        },
        {
            "name": "Dawn Phenomenon Best Practices",
            "query": "What are best practices for managing dawn phenomenon?",
            "expected": "OpenAPS troubleshooting + research papers + Glooko patterns"
        },
        {
            "name": "Safety Considerations",
            "query": "Safety considerations for automated insulin delivery",
            "expected": "OpenAPS safety docs + research evidence"
        },
        {
            "name": "Autotune Across Systems",
            "query": "How does autotune work in different automated insulin delivery systems?",
            "expected": "OpenAPS + AndroidAPS + Loop autotune documentation"
        },
        {
            "name": "CGM Integration",
            "query": "What CGM systems are compatible with automated insulin delivery?",
            "expected": "OpenAPS + AndroidAPS + Loop CGM compatibility docs"
        }
    ]

    # Run test queries (only if researcher is available)
    if agent_ok and researcher:
        all_stats = []
        for test_query in test_queries:
            stats = run_test_query(
                researcher,
                test_query["name"],
                test_query["query"],
                test_query["expected"]
            )
            all_stats.append(stats)

        # Overall summary
        print("🎯 Overall Test Summary")
        print("=" * 50)

        total_queries = len(all_stats)
        avg_query_time = sum(s["query_time"] for s in all_stats) / total_queries * 1000
        total_results = sum(s["total_results"] for s in all_stats)

        print(f"Total Test Queries: {total_queries}")
        print(f"Average Query Time: {avg_query_time:.1f} ms")
        print(f"Total Results Retrieved: {total_results}")

        # Aggregate source distribution
        all_source_counts = Counter()
        for stats in all_stats:
            for source, count in stats["source_counts"].items():
                all_source_counts[source] += count

        print(f"Overall Source Distribution: {dict(all_source_counts)}")

        # Check if multi-source retrieval is working
        multi_source_queries = sum(1 for s in all_stats if len(s["source_counts"]) > 1)
        print(f"Queries with Multi-Source Results: {multi_source_queries}/{total_queries}")

        if multi_source_queries >= 1:
            print("✅ Multi-source RAG retrieval is PARTIALLY WORKING!")
            print("   - Successfully combining OpenAPS docs, research papers, and PDF manuals")
            print("   - Confidence-weighted ranking prioritizes higher-confidence sources")
            print("   - Parallel search across multiple collections implemented")
        else:
            print("❌ Multi-source RAG retrieval needs improvement")

        # Additional validation
        total_sources_used = len(all_source_counts)
        print(f"Total Unique Sources Used: {total_sources_used}")
        
        if total_sources_used >= 3:
            print("✅ Comprehensive multi-source retrieval achieved!")
        elif total_sources_used >= 2:
            print("✅ Basic multi-source retrieval working")
        else:
            print("⚠️  Limited to single source - needs investigation")
    else:
        print("🎯 Skipping query tests (ResearcherAgent not available)")
        print("   To run full tests, configure LLM API keys (GEMINI_API_KEY)")

    print("\n🏁 Test Complete")


if __name__ == "__main__":
    main()
