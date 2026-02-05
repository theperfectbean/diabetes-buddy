#!/usr/bin/env python3
"""
Comprehensive ChromaDB Query Pipeline Diagnostics

Diagnoses WHY "dawn phenomenon" queries fail to retrieve results
despite having 5 populated collections.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(".env"))

def section(title):
    print(f"\n{'=' * 70}")
    print(f"=== {title} ===")
    print('=' * 70)

def subsection(title):
    print(f"\n--- {title} ---")

# =============================================================================
# TEST QUERY - The one that fails
# =============================================================================
TEST_QUERY = "dawn phenomenon basal insulin closed loop"
EXPECTED_COLLECTIONS = ["openaps_docs", "loop_docs", "androidaps_docs", "wikipedia_education", "research_papers"]

section("ChromaDB Query Diagnostics")
print(f"Test Query: \"{TEST_QUERY}\"")
print(f"Expected Collections: {EXPECTED_COLLECTIONS}")

# =============================================================================
# Check 1: ChromaDB Collections
# =============================================================================
section("ChromaDB Collection Diagnostics")
try:
    import chromadb
    from chromadb.config import Settings

    db_path = Path(".cache/chromadb")
    client = chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(anonymized_telemetry=False)
    )

    collections = client.list_collections()
    print(f"Collections found: {len(collections)}")

    collection_info = {}
    for coll in collections:
        count = coll.count()
        collection_info[coll.name] = {
            'count': count,
            'metadata': coll.metadata
        }
        status = "✓" if count > 0 else "✗ EMPTY"
        print(f"  - {coll.name}: {count} chunks {status}")

    # Check for expected collections
    subsection("Expected Collection Check")
    for exp_coll in EXPECTED_COLLECTIONS:
        if exp_coll in collection_info:
            count = collection_info[exp_coll]['count']
            if count > 0:
                print(f"  ✓ {exp_coll}: {count} chunks")
            else:
                print(f"  ✗ {exp_coll}: EMPTY (0 chunks)")
        else:
            print(f"  ✗ {exp_coll}: NOT FOUND")

except Exception as e:
    print(f"✗ ChromaDB access failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# =============================================================================
# Check 2: Embedding Model Consistency
# =============================================================================
section("Embedding Model Check")
try:
    from agents.llm_provider import LLMFactory

    llm = LLMFactory.get_provider()

    # Get configured embedding model
    if hasattr(llm, 'embedding_model'):
        embed_model = llm.embedding_model
    else:
        embed_model = "unknown"

    print(f"Current model: {embed_model}")

    # Check collection metadata for embedding info
    subsection("Collection Metadata")
    for exp_coll in EXPECTED_COLLECTIONS:
        if exp_coll in collection_info:
            meta = collection_info[exp_coll]['metadata']
            print(f"  {exp_coll}: {meta}")
        else:
            print(f"  {exp_coll}: NOT FOUND")

    print(f"\nStatus: (metadata doesn't store embedding model - check dimensions instead)")

except Exception as e:
    print(f"✗ Embedding model check failed: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# Check 3: Query Embedding Test
# =============================================================================
section("Query Embedding Test")
try:
    from agents.llm_provider import LLMFactory

    llm = LLMFactory.get_provider()
    print(f"Query: \"{TEST_QUERY}\"")

    query_embedding = llm.embed_text(TEST_QUERY)

    # Handle nested list
    if isinstance(query_embedding, list) and len(query_embedding) > 0:
        if isinstance(query_embedding[0], list):
            query_embedding = query_embedding[0]

    dim = len(query_embedding)
    sample = query_embedding[:5]

    print(f"Status: ✓ SUCCESS")
    print(f"Dimensions: {dim}")
    print(f"Sample: {[round(v, 4) for v in sample]}")

except Exception as e:
    print(f"Status: ✗ FAILED")
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# =============================================================================
# Check 4: Direct ChromaDB Search
# =============================================================================
section("Direct ChromaDB Search")
try:
    for coll_name in EXPECTED_COLLECTIONS:
        if coll_name not in collection_info:
            print(f"{coll_name}: NOT FOUND")
            continue

        if collection_info[coll_name]['count'] == 0:
            print(f"{coll_name}: EMPTY (0 chunks)")
            continue

        collection = client.get_collection(name=coll_name)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=3
        )

        num_results = len(results['ids'][0]) if results['ids'] and results['ids'][0] else 0

        if num_results > 0:
            distances = [round(d, 3) for d in results['distances'][0]]
            preview = results['documents'][0][0][:100] if results['documents'][0] else "N/A"
            print(f"{coll_name}: {num_results} results (distances: {distances})")
            print(f"  Result 1: \"{preview}...\"")
        else:
            print(f"{coll_name}: ✗ 0 results")

except Exception as e:
    print(f"✗ Direct search failed: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# Check 5: ResearcherAgent Search Path
# =============================================================================
section("ResearcherAgent Search")
try:
    from agents.researcher_chromadb import ResearcherAgent

    researcher = ResearcherAgent(use_chromadb=True)

    # Test openaps_docs search
    subsection("search_openaps_docs()")
    results = researcher.backend.search_openaps_docs(TEST_QUERY, top_k=3)
    print(f"Results count: {len(results)}")
    for i, r in enumerate(results[:3], 1):
        print(f"  [{i}] Confidence: {r.confidence:.2f}")
        print(f"      Quote: \"{r.quote[:80]}...\"")

    # Test loop_docs search
    subsection("search_loop_docs()")
    results = researcher.backend.search_loop_docs(TEST_QUERY, top_k=3)
    print(f"Results count: {len(results)}")
    for i, r in enumerate(results[:3], 1):
        print(f"  [{i}] Confidence: {r.confidence:.2f}")
        print(f"      Quote: \"{r.quote[:80]}...\"")

    # Test query_knowledge (comprehensive search)
    subsection("query_knowledge() - searches all 5 collections")
    results = researcher.query_knowledge(TEST_QUERY, top_k=5)
    print(f"Results count: {len(results)}")
    for i, r in enumerate(results[:5], 1):
        print(f"  [{i}] Source: {r.source}, Confidence: {r.confidence:.2f}")
        print(f"      Quote: \"{r.quote[:80]}...\"")

except Exception as e:
    print(f"✗ ResearcherAgent search failed: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# Check 6: Full Query Path Trace
# =============================================================================
section("Full Query Path Trace")
try:
    from agents.triage import TriageAgent, QueryCategory

    triage = TriageAgent()

    # Step 1: Classification
    subsection("Step 1: Classification")
    classification = triage.classify(TEST_QUERY)
    print(f"Category: {classification.category.value}")
    print(f"Confidence: {classification.confidence:.0%}")
    print(f"Reasoning: {classification.reasoning}")
    print(f"Secondary: {[c.value for c in classification.secondary_categories]}")

    # Step 2: Category to Source Mapping
    subsection("Step 2: Category → Source Mapping")
    category_to_source = {
        "THEORY": "theory",
        "CAMAPS": "camaps",
        "YPSOMED": "ypsomed",
        "LIBRE": "libre",
        "CLINICAL_GUIDELINES": "clinical_guidelines",
    }
    mapped_source = category_to_source.get(classification.category.name, "unknown")
    print(f"Category '{classification.category.name}' maps to source '{mapped_source}'")

    # Check if mapped source exists and has data
    if mapped_source in collection_info:
        count = collection_info[mapped_source]['count']
        if count > 0:
            print(f"  ✓ Collection '{mapped_source}' has {count} chunks")
        else:
            print(f"  ✗ Collection '{mapped_source}' is EMPTY!")
            print(f"  ← PROBLEM: Query classified as {classification.category.name}")
            print(f"             but '{mapped_source}' collection has 0 documents!")
    else:
        print(f"  ✗ Collection '{mapped_source}' NOT FOUND!")

    # Step 3: Full pipeline
    subsection("Step 3: Full Triage Pipeline")
    response = triage.process(TEST_QUERY, verbose=False)

    total_chunks = sum(len(chunks) for chunks in response.results.values())
    print(f"Search results: {total_chunks} total chunks")
    for source, chunks in response.results.items():
        if chunks:
            print(f"  ✓ {source}: {len(chunks)} chunks")
        else:
            print(f"  - {source}: 0 chunks")

    print(f"\nSynthesized Answer Preview:")
    answer_preview = response.synthesized_answer[:200]
    print(f"  \"{answer_preview}...\"")

    if "No relevant information" in response.synthesized_answer:
        print(f"\n  ✗ PROBLEM: Answer contains 'No relevant information'")
    else:
        print(f"\n  ✓ Answer contains content")

except Exception as e:
    print(f"✗ Full query path failed: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# ROOT CAUSE DIAGNOSIS
# =============================================================================
section("ROOT CAUSE DIAGNOSIS")

# Analyze findings
issues = []

# Issue 1: Theory collection empty but THEORY queries go there
if "theory" in collection_info and collection_info["theory"]["count"] == 0:
    issues.append({
        "issue": "THEORY collection is EMPTY",
        "impact": "Queries classified as THEORY (like 'dawn phenomenon') return no results",
        "fix": "Route THEORY queries to query_knowledge() which searches openaps_docs, loop_docs, etc."
    })

# Issue 2: Check if triage doesn't search the populated collections
if "research_papers" in collection_info and collection_info["research_papers"]["count"] == 0:
    issues.append({
        "issue": "research_papers collection is EMPTY (but researchpapers may exist)",
        "impact": "Research paper searches return no results",
        "fix": "Check for collection name mismatch (research_papers vs researchpapers)"
    })

# Issue 3: Triage doesn't route to the new collections
issues.append({
    "issue": "TriageAgent._search_categories() doesn't search openaps_docs/loop_docs/androidaps_docs",
    "impact": "THEORY queries only search 'theory' collection (empty), not the populated knowledge collections",
    "fix": "Update _search_categories() to include query_knowledge() for THEORY queries"
})

if issues:
    print("Issues Found:")
    for i, issue in enumerate(issues, 1):
        print(f"\n{i}. {issue['issue']}")
        print(f"   Impact: {issue['impact']}")
        print(f"   Fix: {issue['fix']}")
else:
    print("✓ No issues found - query pipeline appears healthy")

print("\n" + "=" * 70)
print("DIAGNOSTICS COMPLETE")
print("=" * 70)
