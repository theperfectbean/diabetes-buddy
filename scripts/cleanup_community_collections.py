#!/usr/bin/env python3
"""
Cleanup Community System Collections

Removes OpenAPS, Loop, and AndroidAPS collections from ChromaDB as part of 
the device-aware knowledge prioritization initiative.
"""

import chromadb
from pathlib import Path


def cleanup_community_collections():
    """Delete community system collections from ChromaDB."""
    
    # Get ChromaDB path
    project_root = Path(__file__).parent.parent
    db_path = project_root / ".cache" / "chromadb"
    
    if not db_path.exists():
        print("ChromaDB directory not found. Nothing to clean up.")
        return
    
    client = chromadb.PersistentClient(path=str(db_path))
    
    # Collections to remove
    collections_to_remove = [
        "openaps_docs",
        "openapsdocs",
        "loop_docs",
        "loopdocs",
        "androidaps_docs",
        "androidapsdocs"
    ]
    
    print("Cleaning up community system collections...")
    removed_count = 0
    
    for name in collections_to_remove:
        try:
            client.delete_collection(name)
            print(f"✓ Deleted: {name}")
            removed_count += 1
        except Exception as e:
            # Collection probably doesn't exist
            print(f"✗ Skipped {name}: {str(e)}")
    
    print(f"\nCompleted: {removed_count} collection(s) removed")
    
    # List remaining collections
    print("\nRemaining collections:")
    try:
        collections = client.list_collections()
        for coll in collections:
            count = coll.count()
            print(f"  - {coll.name}: {count} chunks")
    except Exception as e:
        print(f"  Could not list collections: {e}")


if __name__ == "__main__":
    cleanup_community_collections()
