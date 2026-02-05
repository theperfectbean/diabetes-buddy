#!/usr/bin/env python3
"""
Fix ChromaDB embedding dimension mismatches

Deletes collections with wrong embedding dimensions (768-dim from old model).
Working collections with correct dimensions (384-dim) are preserved.
"""

import chromadb
from chromadb.config import Settings
from pathlib import Path
import sys

def main():
    # Connect to ChromaDB
    db_path = Path(__file__).parent.parent / ".cache" / "chromadb"
    client = chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(anonymized_telemetry=False)
    )

    print("=" * 70)
    print("ChromaDB Embedding Dimension Fix")
    print("=" * 70)

    # Identify broken collections
    working = []
    broken = []

    print("\nScanning collections...")
    for coll in client.list_collections():
        try:
            if coll.count() > 0:
                # Test if collection works with current embedding model
                result = coll.query(query_texts=["test"], n_results=1)
                working.append((coll.name, coll.count()))
        except Exception as e:
            if "dimension" in str(e):
                broken.append((coll.name, coll.count()))

    print(f"\n✓ Working collections: {len(working)}")
    for name, count in sorted(working):
        print(f"  • {name} ({count} chunks)")

    print(f"\n⚠ Broken collections (wrong dimensions): {len(broken)}")
    for name, count in sorted(broken):
        print(f"  • {name} ({count} chunks)")

    if not broken:
        print("\n✅ All collections have correct dimensions!")
        return 0

    # Confirm deletion
    print("\n" + "=" * 70)
    print("SOLUTION: Delete broken collections")
    print("=" * 70)
    print("\nThese collections use 768-dim embeddings (old model).")
    print("Current system uses 384-dim embeddings (new model).")
    print("\nBroken collections will be deleted and can be re-ingested if needed.")
    print("Working collections will be preserved.")
    
    response = input("\nProceed with deletion? (yes/no): ").strip().lower()
    
    if response != "yes":
        print("❌ Aborted. No changes made.")
        return 1

    # Delete broken collections
    print("\nDeleting broken collections...")
    deleted_count = 0
    for name, count in broken:
        try:
            client.delete_collection(name)
            print(f"  ✓ Deleted: {name}")
            deleted_count += 1
        except Exception as e:
            print(f"  ✗ Failed to delete {name}: {e}")

    print("\n" + "=" * 70)
    print(f"✅ Cleanup complete! Deleted {deleted_count}/{len(broken)} collections")
    print("=" * 70)
    
    print("\nNext steps:")
    print("1. Re-ingest important documents if needed")
    print("2. Verify queries work: python test_comprehensive.py")
    print("\nNote: Device manuals (camaps, libre, ypsomed) are still working!")

    return 0

if __name__ == "__main__":
    sys.exit(main())
