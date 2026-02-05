#!/usr/bin/env python3
"""
Clean up deleted OpenAPS, Loop, and AndroidAPS ChromaDB collections.

These collections were created from deleted documentation sources and should
be removed to keep the knowledge base clean.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import chromadb
from chromadb.config import Settings


def cleanup_collections():
    """Delete the three removed documentation collections."""
    # Initialize ChromaDB client
    db_path = project_root / ".cache" / "chromadb"
    db_path.mkdir(parents=True, exist_ok=True)
    
    client = chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(anonymized_telemetry=False)
    )
    
    # Collections to delete
    collections_to_delete = [
        'openapsdocs',
        'loopdocs',
        'androidapsdocs'
    ]
    
    print("=" * 70)
    print("ChromaDB Collection Cleanup")
    print("=" * 70)
    print()
    
    # List all collections before
    all_collections_before = client.list_collections()
    collection_names_before = [col.name for col in all_collections_before]
    
    print(f"Collections BEFORE cleanup ({len(collection_names_before)} total):")
    for col in sorted(collection_names_before):
        print(f"  - {col}")
    print()
    
    # Delete each collection
    deleted = []
    failed = []
    
    for collection_name in collections_to_delete:
        try:
            # Check if collection exists
            existing = client.list_collections()
            exists = any(col.name == collection_name for col in existing)
            
            if exists:
                client.delete_collection(name=collection_name)
                deleted.append(collection_name)
                print(f"✅ Deleted: {collection_name}")
            else:
                print(f"⏭️  Skipped: {collection_name} (does not exist)")
        except Exception as e:
            failed.append((collection_name, str(e)))
            print(f"❌ Failed to delete {collection_name}: {e}")
    
    print()
    
    # List all collections after
    all_collections_after = client.list_collections()
    collection_names_after = [col.name for col in all_collections_after]
    
    print(f"Collections AFTER cleanup ({len(collection_names_after)} total):")
    for col in sorted(collection_names_after):
        print(f"  - {col}")
    print()
    
    # Summary
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Deleted: {len(deleted)}")
    for col in deleted:
        print(f"  ✅ {col}")
    
    if failed:
        print(f"\nFailed: {len(failed)}")
        for col, err in failed:
            print(f"  ❌ {col}: {err}")
    
    print(f"\nTotal collections before: {len(collection_names_before)}")
    print(f"Total collections after: {len(collection_names_after)}")
    print(f"Removed: {len(collection_names_before) - len(collection_names_after)}")
    print()
    
    # Verify the three sources are gone
    remaining_to_remove = [
        col for col in collection_names_after
        if col in ['openapsdocs', 'loopdocs', 'androidapsdocs']
    ]
    
    if remaining_to_remove:
        print(f"⚠️  Warning: {len(remaining_to_remove)} collections still present:")
        for col in remaining_to_remove:
            print(f"  - {col}")
        return False
    else:
        print("✅ All target collections successfully removed!")
        return True


if __name__ == "__main__":
    try:
        success = cleanup_collections()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
