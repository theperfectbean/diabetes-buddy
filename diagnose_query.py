#!/usr/bin/env python3
"""
Comprehensive diagnostics for the query pipeline.
Tests before and after to identify where the failure occurs.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(".env"))

print("=" * 80)
print("COMPREHENSIVE QUERY PIPELINE DIAGNOSTICS")
print("=" * 80)

# Test 1: Verify embedding model availability
print("\n[TEST 1] Gemini Embedding Model Availability")
print("-" * 80)
try:
    from google import genai
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    
    result = client.models.embed_content(
        model="models/gemini-embedding-001",
        contents="Test embedding"
    )
    print(f"✓ Embedding model available")
    print(f"  Model: models/gemini-embedding-001")
    print(f"  Dimension: {len(result.embeddings[0].values)}")
except Exception as e:
    print(f"✗ Embedding model failed: {e}")
    sys.exit(1)

# Test 2: Check ChromaDB Backend configuration
print("\n[TEST 2] ChromaDB Backend Configuration")
print("-" * 80)
try:
    from agents.researcher_chromadb import ChromaDBBackend
    
    backend = ChromaDBBackend()
    print(f"✓ ChromaDBBackend initialized")
    print(f"  Configured embedding model: {backend.embedding_model}")
    
    # Check collections
    collections = backend.chroma_client.list_collections()
    print(f"  Collections found: {len(collections)}")
    for coll in collections:
        count = coll.count()
        print(f"    - {coll.name}: {count} documents")
        
except Exception as e:
    print(f"✗ ChromaDB initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Test single collection search
print("\n[TEST 3] Direct Collection Search (camaps)")
print("-" * 80)
try:
    test_text = "What is Ease-off mode?"
    print(f"Query text: '{test_text}'")
    print("Embedding query...")
    
    result = client.models.embed_content(
        model="models/gemini-embedding-001",
        contents=test_text
    )
    query_embedding = result.embeddings[0].values
    print(f"  ✓ Query embedded ({len(query_embedding)} dimensions)")
    
    # Get camaps collection
    camaps_collection = backend.chroma_client.get_collection("camaps")
    print(f"  ✓ Got camaps collection ({camaps_collection.count()} documents)")
    
    # Search
    search_results = camaps_collection.query(
        query_embeddings=[query_embedding],
        n_results=5
    )
    
    print(f"  ✓ Search completed")
    print(f"    Results found: {len(search_results['ids'][0])}")
    
    if search_results['ids'][0]:
        print(f"    Top result distance: {search_results['distances'][0][0]:.4f}")
        print(f"    Top result text: {search_results['documents'][0][0][:100]}...")
    else:
        print(f"    ✗ NO RESULTS FOUND!")
        
except Exception as e:
    print(f"✗ Direct search failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Test researcher backend
print("\n[TEST 4] Researcher Backend Search")
print("-" * 80)
try:
    from agents.researcher_chromadb import ChromaDBBackend
    
    backend = ChromaDBBackend()
    test_query = "What is Ease-off mode in CamAPS?"
    
    print(f"Query: '{test_query}'")
    print("Searching all sources...")
    
    results = backend.search(test_query, top_k=5)
    
    print(f"✓ Search completed")
    print(f"  Total results: {sum(len(r) for r in results.values())}")
    
    for source, chunks in results.items():
        if chunks:
            print(f"  ✓ {source}: {len(chunks)} chunks")
            for i, chunk in enumerate(chunks[:2], 1):
                print(f"    [{i}] Confidence: {chunk.confidence:.2f}")
                print(f"        Text: {chunk.quote[:80]}...")
        else:
            print(f"  - {source}: no results")
            
except Exception as e:
    print(f"✗ Researcher search failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Test full triage pipeline
print("\n[TEST 5] Full Triage Pipeline")
print("-" * 80)
try:
    from agents.triage import TriageAgent
    
    triage = TriageAgent()
    test_query = "What is Ease-off mode in CamAPS?"
    
    print(f"Query: '{test_query}'")
    print("Running triage pipeline...")
    
    result = triage.process(test_query, verbose=True)
    
    print(f"\n✓ Triage completed")
    print(f"  Classification: {result.classification.category} ({result.classification.confidence:.1%})")
    
    total_chunks = sum(len(chunks) for chunks in result.results.values())
    print(f"  Total search results: {total_chunks}")
    
    for source, chunks in result.results.items():
        if chunks:
            print(f"    ✓ {source}: {len(chunks)} chunks")
        else:
            print(f"    - {source}: 0 chunks")
    
    print(f"\n  Final Answer:")
    print(f"  {result.synthesized_answer}")
    
    if "No relevant information" in result.synthesized_answer:
        print(f"\n  ✗ PROBLEM: Query still returning 'No relevant information'")
        print(f"  Chunks found: {total_chunks} (but synthesizer says 'none')")
        sys.exit(1)
    else:
        print(f"\n  ✓ SUCCESS: Query returned relevant information")
        
except Exception as e:
    print(f"✗ Triage pipeline failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("ALL DIAGNOSTICS PASSED ✓")
print("=" * 80)
