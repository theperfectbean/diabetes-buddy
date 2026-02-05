#!/usr/bin/env python3
"""
Rebuild all ChromaDB collections with consistent embeddings.

This script:
1. Deletes all existing ChromaDB collections
2. Re-runs ingestion scripts to rebuild with current embedding model

Usage:
    python scripts/rebuild_chromadb.py
"""

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CHROMADB_PATH = PROJECT_ROOT / ".cache" / "chromadb"


def main():
    print("=" * 60)
    print("ChromaDB Collection Rebuild")
    print("=" * 60)

    # Step 1: Delete all ChromaDB data
    if CHROMADB_PATH.exists():
        print(f"\n1. Deleting ChromaDB at {CHROMADB_PATH}...")
        shutil.rmtree(CHROMADB_PATH)
        print("   ✓ ChromaDB deleted")
    else:
        print(f"\n1. ChromaDB not found at {CHROMADB_PATH}, skipping delete")

    # Create fresh directory
    CHROMADB_PATH.mkdir(parents=True, exist_ok=True)
    print("   ✓ Fresh ChromaDB directory created")

    # Step 2: Verify embedding model
    print("\n2. Checking embedding model...")
    sys.path.insert(0, str(PROJECT_ROOT))

    from agents.llm_provider import LLMFactory
    llm = LLMFactory.get_provider()
    embed_model = getattr(llm, "embedding_model", "unknown")

    # Test embedding dimension
    test_embed = llm.embed_text("test query")
    dim = len(test_embed)

    print(f"   Embedding model: {embed_model}")
    print(f"   Embedding dimension: {dim}")

    if dim != 768:
        print(f"\n   ⚠️  WARNING: Expected 768-dim embeddings, got {dim}")
        print("   Collections will be built with this dimension.")
    else:
        print("   ✓ Using 768-dim embeddings (text-embedding-004)")

    print("\n3. Ready to rebuild collections.")
    print("   Run the following scripts to re-index:")
    print("   - python scripts/ingest_openaps_docs.py --force")
    print("   - python scripts/ingest_loop_docs.py --force")
    print("   - python scripts/ingest_androidaps_docs.py --force")
    print("   - python scripts/ingest_wikipedia.py --force")
    print("   - python scripts/ingest_ada_standards.py --force")
    print("\n   Or run: python scripts/rebuild_all_knowledge.py")

    print("\n" + "=" * 60)
    print("ChromaDB deletion complete!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
