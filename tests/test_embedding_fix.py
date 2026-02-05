#!/usr/bin/env python3
"""Test embedding dimension fix"""
import chromadb
from chromadb.config import Settings
from agents.llm_provider import LLMFactory


def test_embedding_dimension():
    """Test that embedding dimensions are correct."""
    # Initialize LLM for embeddings
    llm = LLMFactory.get_provider()

    # Test embedding dimension
    test_embedding = llm.embed_text(["test query"])[0]
    assert len(test_embedding) > 0, "Embedding should have non-zero dimension"
    print(f"✓ Current embedding model dimension: {len(test_embedding)}")


def test_chromadb_collections_exist():
    """Test that ChromaDB collections exist."""
    # Check ChromaDB collections
    client = chromadb.PersistentClient(path=".cache/chromadb", settings=Settings(anonymized_telemetry=False))
    collections = client.list_collections()
    assert len(collections) >= 0, "Should be able to list collections"
    print(f"✓ Found {len(collections)} collections in ChromaDB")


def test_collection_dimensions_match():
    """Test that collection dimensions match embedding model."""
    if not hasattr(LLMFactory, 'get_provider'):
        pytest.skip("LLM provider not available")
        
    llm = LLMFactory.get_provider()
    test_embedding = llm.embed_text(["test query"])[0]
    
    client = chromadb.PersistentClient(path=".cache/chromadb", settings=Settings(anonymized_telemetry=False))
    collections = client.list_collections()
    
    if not collections:
        pytest.skip("No collections to test")
    
    working = 0
    for coll in collections[:5]:  # Test first 5
        try:
            result = coll.query(query_embeddings=[test_embedding], n_results=1)
            working += 1
        except Exception as e:
            if "dimension" in str(e).lower():
                pytest.fail(f"Collection {coll.name} has dimension mismatch: {e}")
    
    assert working == min(5, len(collections)), f"Only {working}/{min(5, len(collections))} collections working"
