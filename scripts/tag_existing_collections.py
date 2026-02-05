#!/usr/bin/env python3
"""
One-time migration script to tag existing ChromaDB collections with type metadata.

Uses heuristic rules to determine collection types:
- "clinical_guideline": Standards/guidelines collections (ADA, NHS, Australian)
- "knowledge_base": Research/education collections (OpenAPS, Loop, Wikipedia, PubMed)
- "device_manual": User-uploaded device manuals (default for user uploads)

Usage:
    python scripts/tag_existing_collections.py --dry-run   # Preview changes
    python scripts/tag_existing_collections.py              # Apply changes
"""

import argparse
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings


# Heuristic rules for classifying collections by name
CLINICAL_GUIDELINE_PATTERNS = [
    "standards", "guidelines", "ada_", "nhs_", "australian_",
]

KNOWLEDGE_BASE_PATTERNS = [
    "openaps", "loop", "androidaps", "wikipedia", "research",
    "pubmed",
]


def classify_collection(name: str) -> str:
    """Determine collection type from its name using heuristic rules."""
    name_lower = name.lower()

    for pattern in CLINICAL_GUIDELINE_PATTERNS:
        if pattern in name_lower or name_lower.startswith(pattern):
            return "clinical_guideline"

    for pattern in KNOWLEDGE_BASE_PATTERNS:
        if pattern in name_lower or name_lower.startswith(pattern):
            return "knowledge_base"

    # Default: treat as device manual (user uploads)
    return "device_manual"


def main():
    parser = argparse.ArgumentParser(
        description="Tag existing ChromaDB collections with type metadata"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them",
    )
    parser.add_argument(
        "--db-path",
        default=".cache/chromadb",
        help="Path to ChromaDB database (default: .cache/chromadb)",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Error: Database path '{db_path}' does not exist.")
        sys.exit(1)

    client = chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(anonymized_telemetry=False),
    )

    collections = client.list_collections()
    if not collections:
        print("No collections found in database.")
        return

    print(f"\n{'Collection':<45} {'Detected Type':<20} {'Chunks':<8} {'Status'}")
    print("-" * 90)

    success_count = 0
    error_count = 0

    for col in collections:
        col_type = classify_collection(col.name)
        chunk_count = col.count()
        existing_meta = col.metadata or {}
        existing_type = existing_meta.get("type")

        if existing_type == col_type:
            status = "already tagged"
        elif args.dry_run:
            status = "would tag"
        else:
            try:
                # Exclude hnsw:* keys - ChromaDB doesn't allow re-setting distance function
                filtered_meta = {k: v for k, v in existing_meta.items() if not k.startswith("hnsw:")}
                new_metadata = {**filtered_meta, "type": col_type, "source_category": col_type}
                col.modify(metadata=new_metadata)
                status = "tagged"
                success_count += 1
            except Exception as e:
                status = f"ERROR: {e}"
                error_count += 1

        print(f"{col.name:<45} {col_type:<20} {chunk_count:<8} {status}")

    print("-" * 90)

    if args.dry_run:
        print(f"\nDry run complete. {len(collections)} collections would be tagged.")
        print("Run without --dry-run to apply changes.")
    else:
        print(f"\nDone. {success_count} tagged, {error_count} errors, "
              f"{len(collections) - success_count - error_count} already tagged.")


if __name__ == "__main__":
    main()
