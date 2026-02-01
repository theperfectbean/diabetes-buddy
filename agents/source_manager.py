"""
User Source Manager for Diabetes Buddy

Manages user-uploaded PDFs and their integration into the ChromaDB knowledge base.
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class UserSource:
    """Represents a user-uploaded source document."""
    filename: str
    display_name: str
    file_path: str
    collection_key: str
    uploaded_at: str
    file_hash: str
    indexed: bool = False
    chunk_count: int = 0


class UserSourceManager:
    """
    Manages user-uploaded PDF sources.

    Responsibilities:
    - Store uploaded PDFs in docs/user-sources/
    - Generate ChromaDB collection keys from filenames
    - Track upload metadata in sources.json
    - Provide list/delete operations
    """

    USER_SOURCES_DIR = "docs/user-sources"
    METADATA_FILE = "sources.json"

    def __init__(self, project_root: Optional[Path] = None):
        if project_root is None:
            project_root = Path(__file__).parent.parent
        self.project_root = Path(project_root)
        self.sources_dir = self.project_root / self.USER_SOURCES_DIR
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.sources_dir / self.METADATA_FILE
        self._load_metadata()

    def _load_metadata(self):
        """Load or create sources metadata."""
        if self.metadata_path.exists():
            with open(self.metadata_path, 'r') as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {"sources": [], "version": "1.0.0"}
            self._save_metadata()

    def _save_metadata(self):
        """Persist metadata to disk."""
        with open(self.metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

    def _generate_collection_key(self, filename: str) -> str:
        """Generate ChromaDB-safe collection key from filename."""
        name = Path(filename).stem.lower()
        for char in [' ', '-', '.', '(', ')', '[', ']', ',']:
            name = name.replace(char, '_')
        while '__' in name:
            name = name.replace('__', '_')
        # Prefix with user_, limit to 63 chars total
        return f"user_{name.strip('_')[:55]}"

    def _compute_file_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of file content."""
        return hashlib.sha256(content).hexdigest()[:16]

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage."""
        name = Path(filename).name
        for char in ['/', '\\', '..', '\x00']:
            name = name.replace(char, '_')
        return name

    def _generate_display_name(self, filename: str) -> str:
        """Generate human-readable display name."""
        name = Path(filename).stem
        name = name.replace('_', ' ').replace('-', ' ')
        return name.title()

    def add_source(self, filename: str, content: bytes) -> UserSource:
        """
        Add a new user source PDF.

        Args:
            filename: Original filename
            content: PDF file content as bytes

        Returns:
            UserSource object
        """
        safe_filename = self._sanitize_filename(filename)
        collection_key = self._generate_collection_key(safe_filename)
        file_hash = self._compute_file_hash(content)

        # Check for duplicates by hash
        for existing in self.metadata["sources"]:
            if existing.get("file_hash") == file_hash:
                raise ValueError(f"This file has already been uploaded as '{existing['filename']}'")

        # Save file
        file_path = self.sources_dir / safe_filename
        with open(file_path, 'wb') as f:
            f.write(content)

        # Create source record
        source = UserSource(
            filename=safe_filename,
            display_name=self._generate_display_name(safe_filename),
            file_path=str(file_path),
            collection_key=collection_key,
            uploaded_at=datetime.now().isoformat(),
            file_hash=file_hash,
            indexed=False,
            chunk_count=0
        )

        # Add to metadata
        self.metadata["sources"].append(asdict(source))
        self._save_metadata()

        return source

    def list_sources(self) -> List[UserSource]:
        """List all user sources."""
        return [UserSource(**s) for s in self.metadata.get("sources", [])]

    def get_source(self, collection_key: str) -> Optional[UserSource]:
        """Get a specific source by collection key."""
        for s in self.metadata.get("sources", []):
            if s.get("collection_key") == collection_key:
                return UserSource(**s)
        return None

    def get_source_by_filename(self, filename: str) -> Optional[UserSource]:
        """Get a source by its filename."""
        for s in self.metadata.get("sources", []):
            if s.get("filename") == filename:
                return UserSource(**s)
        return None

    def delete_source(self, filename: str) -> bool:
        """
        Delete a user source.

        Args:
            filename: The filename to delete

        Returns:
            True if deleted, False if not found
        """
        source_to_delete = None
        for s in self.metadata["sources"]:
            if s.get("filename") == filename:
                source_to_delete = s
                break

        if not source_to_delete:
            return False

        # Delete file
        file_path = Path(source_to_delete["file_path"])
        if file_path.exists():
            file_path.unlink()

        # Remove from metadata
        self.metadata["sources"] = [
            s for s in self.metadata["sources"]
            if s.get("filename") != filename
        ]
        self._save_metadata()

        return True

    def mark_indexed(self, collection_key: str, chunk_count: int):
        """Mark a source as indexed in ChromaDB."""
        for s in self.metadata["sources"]:
            if s.get("collection_key") == collection_key:
                s["indexed"] = True
                s["chunk_count"] = chunk_count
                s["indexed_at"] = datetime.now().isoformat()
                break
        self._save_metadata()

    def get_pending_sources(self) -> List[UserSource]:
        """Get sources that need indexing."""
        return [
            UserSource(**s)
            for s in self.metadata.get("sources", [])
            if not s.get("indexed", False)
        ]