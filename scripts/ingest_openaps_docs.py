#!/usr/bin/env python3
"""
OpenAPS Community Documentation Ingestion Script

Git-based auto-update system for ingesting documentation from:
- OpenAPS docs (https://github.com/openaps/docs)
- AndroidAPS docs (https://github.com/openaps/AndroidAPSdocs)
- Loop docs (https://github.com/LoopKit/loopdocs)

Usage:
    python scripts/ingest_openaps_docs.py --clone    # First time setup
    python scripts/ingest_openaps_docs.py --update   # Check for updates
    python scripts/ingest_openaps_docs.py --force    # Re-process everything
    python scripts/ingest_openaps_docs.py --diff     # Show what changed
"""

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Set up logging
_logs_dir = PROJECT_ROOT / "logs"
_logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(_logs_dir / 'knowledge_updates.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

REPO_CONFIG = {
    "openaps": {
        "url": "https://github.com/openaps/docs.git",
        "branch": "master",
        "display_name": "OpenAPS Documentation",
        "docs_subdir": "docs",  # Where markdown files are located
        "confidence": 0.8,
    },
    "androidaps": {
        "url": "https://github.com/openaps/AndroidAPSdocs.git",
        "branch": "master",
        "display_name": "AndroidAPS Documentation",
        "docs_subdir": "docs",
        "confidence": 0.8,
    },
    "loop": {
        "url": "https://github.com/LoopKit/loopdocs.git",
        "branch": "main",
        "display_name": "Loop Documentation",
        "docs_subdir": "docs",
        "confidence": 0.8,
    },
}

# Directories - Use data/sources/ for repos as requested
RAW_REPOS_DIR = PROJECT_ROOT / "data" / "sources"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "archive"
UPDATE_LOGS_DIR = PROJECT_ROOT / "data" / "update_logs"
CHANGELOG_PATH = PROJECT_ROOT / "docs" / "community-knowledge" / "CHANGELOG.md"
VERSIONS_FILE = CACHE_DIR / "repo_versions.json"
METADATA_FILE = CACHE_DIR / "openaps_file_metadata.json"

# ChromaDB settings
CHROMADB_PATH = PROJECT_ROOT / ".cache" / "chromadb"
COLLECTION_NAME = "openaps_docs"  # Collection name as requested

# Chunking parameters
CHUNK_SIZE = 500  # words
CHUNK_OVERLAP = 100  # words

# Supported file extensions
SUPPORTED_EXTENSIONS = {'.md', '.rst'}


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class FileMetadata:
    """Metadata for a processed file."""
    file: str
    source_repo: str
    commit_hash: str
    last_updated: str
    commit_message: str
    word_count: int
    processed_at: str
    content_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChangeInfo:
    """Information about a changed file."""
    file_path: str
    change_type: str  # 'modified', 'new', 'deleted'
    commit_hash: str
    commit_message: str
    commit_date: str


@dataclass
class UpdateSummary:
    """Summary of an update run."""
    repo_name: str
    files_updated: int = 0
    files_new: int = 0
    files_deleted: int = 0
    embeddings_created: int = 0
    embeddings_updated: int = 0
    embeddings_deleted: int = 0
    errors: list = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            'repo_name': self.repo_name,
            'files_updated': self.files_updated,
            'files_new': self.files_new,
            'files_deleted': self.files_deleted,
            'embeddings_created': self.embeddings_created,
            'embeddings_updated': self.embeddings_updated,
            'embeddings_deleted': self.embeddings_deleted,
            'errors': self.errors,
            'duration_seconds': (self.end_time - self.start_time).total_seconds() if self.end_time else 0
        }


# =============================================================================
# Git Operations
# =============================================================================

class GitManager:
    """Manages git operations for documentation repos."""

    def __init__(self):
        self.repos_dir = RAW_REPOS_DIR
        self.repos_dir.mkdir(parents=True, exist_ok=True)

    def _run_git(self, repo_path: Path, *args, capture_output: bool = True) -> subprocess.CompletedProcess:
        """Run a git command in the specified repo."""
        cmd = ['git', '-C', str(repo_path)] + list(args)
        logger.debug(f"Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            timeout=300  # 5 minute timeout
        )
        return result

    def clone_repo(self, repo_key: str) -> bool:
        """
        Clone a repository for the first time.

        Args:
            repo_key: Key from REPO_CONFIG

        Returns:
            True if successful
        """
        if repo_key not in REPO_CONFIG:
            logger.error(f"Unknown repo: {repo_key}")
            return False

        config = REPO_CONFIG[repo_key]
        repo_path = self.repos_dir / repo_key

        if repo_path.exists():
            logger.info(f"Repository {repo_key} already exists at {repo_path}")
            return True

        logger.info(f"Cloning {config['display_name']} from {config['url']}...")

        try:
            result = subprocess.run(
                ['git', 'clone', '--depth', '100', '-b', config['branch'], config['url'], str(repo_path)],
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for clone
            )

            if result.returncode != 0:
                logger.error(f"Clone failed: {result.stderr}")
                return False

            logger.info(f"Successfully cloned {repo_key}")
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Clone timed out for {repo_key}")
            return False
        except Exception as e:
            logger.error(f"Clone error for {repo_key}: {e}")
            return False

    def get_current_commit(self, repo_key: str) -> Optional[str]:
        """Get the current HEAD commit hash."""
        repo_path = self.repos_dir / repo_key
        if not repo_path.exists():
            return None

        result = self._run_git(repo_path, 'rev-parse', 'HEAD')
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def fetch_updates(self, repo_key: str) -> bool:
        """
        Fetch updates from remote.

        Args:
            repo_key: Repository key

        Returns:
            True if fetch successful
        """
        repo_path = self.repos_dir / repo_key
        if not repo_path.exists():
            logger.error(f"Repository {repo_key} not found")
            return False

        config = REPO_CONFIG[repo_key]
        logger.info(f"Fetching updates for {config['display_name']}...")

        result = self._run_git(repo_path, 'fetch', 'origin', config['branch'])
        if result.returncode != 0:
            logger.error(f"Fetch failed: {result.stderr}")
            return False

        return True

    def get_remote_commit(self, repo_key: str) -> Optional[str]:
        """Get the latest remote commit hash."""
        repo_path = self.repos_dir / repo_key
        config = REPO_CONFIG[repo_key]

        result = self._run_git(repo_path, 'rev-parse', f'origin/{config["branch"]}')
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def pull_updates(self, repo_key: str) -> bool:
        """Pull updates from remote."""
        repo_path = self.repos_dir / repo_key
        config = REPO_CONFIG[repo_key]

        result = self._run_git(repo_path, 'pull', 'origin', config['branch'])
        if result.returncode != 0:
            logger.error(f"Pull failed: {result.stderr}")
            return False

        return True

    def get_changed_files(self, repo_key: str, old_hash: str, new_hash: str) -> list[ChangeInfo]:
        """
        Get list of changed files between two commits.

        Args:
            repo_key: Repository key
            old_hash: Previous commit hash
            new_hash: New commit hash

        Returns:
            List of ChangeInfo objects
        """
        repo_path = self.repos_dir / repo_key
        changes = []

        # Get list of changed files with status
        result = self._run_git(
            repo_path, 'diff', '--name-status', old_hash, new_hash
        )

        if result.returncode != 0:
            logger.error(f"diff failed: {result.stderr}")
            return changes

        for line in result.stdout.strip().split('\n'):
            if not line:
                continue

            parts = line.split('\t')
            if len(parts) < 2:
                continue

            status = parts[0][0]  # First character: A, M, D, R, etc.
            file_path = parts[-1]  # Last part is the file path

            # Only process markdown and RST files
            if not any(file_path.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                continue

            # Determine change type
            if status == 'A':
                change_type = 'new'
            elif status == 'D':
                change_type = 'deleted'
            else:
                change_type = 'modified'

            # Get commit info for this file
            commit_info = self._get_file_commit_info(repo_path, file_path, new_hash)

            changes.append(ChangeInfo(
                file_path=file_path,
                change_type=change_type,
                commit_hash=commit_info.get('hash', new_hash[:8]),
                commit_message=commit_info.get('message', 'Unknown'),
                commit_date=commit_info.get('date', datetime.now().isoformat())
            ))

        return changes

    def _get_file_commit_info(self, repo_path: Path, file_path: str, ref: str = 'HEAD') -> dict:
        """Get the latest commit info for a specific file."""
        result = self._run_git(
            repo_path, 'log', '-1', '--format=%H|%s|%aI', ref, '--', file_path
        )

        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split('|')
            if len(parts) >= 3:
                return {
                    'hash': parts[0][:8],
                    'message': parts[1],
                    'date': parts[2]
                }

        return {'hash': '', 'message': '', 'date': ''}

    def get_all_markdown_files(self, repo_key: str) -> list[str]:
        """Get all markdown and RST files in a repository."""
        repo_path = self.repos_dir / repo_key
        config = REPO_CONFIG[repo_key]
        docs_dir = repo_path / config.get('docs_subdir', 'docs')

        if not docs_dir.exists():
            # Try root if docs subdir doesn't exist
            docs_dir = repo_path

        doc_files = []
        # Support both .md and .rst files
        for ext in SUPPORTED_EXTENSIONS:
            for doc_file in docs_dir.rglob(f'*{ext}'):
                rel_path = doc_file.relative_to(repo_path)
                doc_files.append(str(rel_path))

        return doc_files


# =============================================================================
# Version Cache Management
# =============================================================================

class VersionCache:
    """Manages cached version information for repos."""

    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._versions = self._load()

    def _load(self) -> dict:
        """Load version cache from file."""
        if VERSIONS_FILE.exists():
            try:
                with open(VERSIONS_FILE, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error loading version cache: {e}")
        return {}

    def save(self) -> None:
        """Save version cache to file."""
        self._versions['last_updated'] = datetime.now().isoformat()
        with open(VERSIONS_FILE, 'w') as f:
            json.dump(self._versions, f, indent=2)
        logger.debug("Saved version cache")

    def get_commit(self, repo_key: str) -> Optional[str]:
        """Get cached commit hash for a repo."""
        return self._versions.get(repo_key, {}).get('commit_hash')

    def set_commit(self, repo_key: str, commit_hash: str) -> None:
        """Set commit hash for a repo."""
        if repo_key not in self._versions:
            self._versions[repo_key] = {}
        self._versions[repo_key]['commit_hash'] = commit_hash
        self._versions[repo_key]['updated_at'] = datetime.now().isoformat()

    def get_all(self) -> dict:
        """Get all version info."""
        return self._versions.copy()


# =============================================================================
# File Metadata Management
# =============================================================================

class MetadataManager:
    """Manages per-file metadata tracking."""

    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._metadata: dict[str, FileMetadata] = self._load()

    def _load(self) -> dict:
        """Load metadata from file."""
        if METADATA_FILE.exists():
            try:
                with open(METADATA_FILE, 'r') as f:
                    data = json.load(f)
                    return {
                        k: FileMetadata(**v) for k, v in data.get('files', {}).items()
                    }
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error loading metadata: {e}")
        return {}

    def save(self) -> None:
        """Save metadata to file."""
        data = {
            'last_updated': datetime.now().isoformat(),
            'file_count': len(self._metadata),
            'files': {k: v.to_dict() for k, v in self._metadata.items()}
        }
        with open(METADATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Saved metadata for {len(self._metadata)} files")

    def get(self, file_key: str) -> Optional[FileMetadata]:
        """Get metadata for a file."""
        return self._metadata.get(file_key)

    def set(self, file_key: str, metadata: FileMetadata) -> None:
        """Set metadata for a file."""
        self._metadata[file_key] = metadata

    def delete(self, file_key: str) -> None:
        """Delete metadata for a file."""
        if file_key in self._metadata:
            del self._metadata[file_key]

    def get_by_repo(self, repo_key: str) -> dict[str, FileMetadata]:
        """Get all metadata for a specific repo."""
        return {
            k: v for k, v in self._metadata.items()
            if v.source_repo == repo_key
        }


# =============================================================================
# Changelog Generation
# =============================================================================

class ChangelogGenerator:
    """Generates changelog for documentation updates."""

    def __init__(self):
        self.changelog_path = CHANGELOG_PATH
        self.changelog_path.parent.mkdir(parents=True, exist_ok=True)

    def add_update(self, date: datetime, repo_name: str, changes: list[ChangeInfo]) -> None:
        """
        Add an update entry to the changelog.

        Args:
            date: Update date
            repo_name: Repository display name
            changes: List of changes
        """
        if not changes:
            return

        # Read existing changelog
        existing_content = ""
        if self.changelog_path.exists():
            with open(self.changelog_path, 'r') as f:
                existing_content = f.read()

        # Generate new entry
        entry = f"\n## {date.strftime('%Y-%m-%d')} Update - {repo_name}\n\n"

        # Group by change type
        new_files = [c for c in changes if c.change_type == 'new']
        modified_files = [c for c in changes if c.change_type == 'modified']
        deleted_files = [c for c in changes if c.change_type == 'deleted']

        if new_files:
            entry += "### New Files\n"
            for change in new_files:
                entry += f"- **{change.file_path}**\n"
                entry += f"  - Commit: \"{change.commit_message}\"\n"

        if modified_files:
            entry += "\n### Modified Files\n"
            for change in modified_files:
                entry += f"- **{change.file_path}**\n"
                entry += f"  - Commit: \"{change.commit_message}\"\n"

        if deleted_files:
            entry += "\n### Deleted Files\n"
            for change in deleted_files:
                entry += f"- ~~{change.file_path}~~\n"

        entry += "\n---\n"

        # Prepend to existing content (after header)
        if existing_content.startswith("# "):
            # Find end of header
            header_end = existing_content.find('\n\n')
            if header_end > 0:
                header = existing_content[:header_end + 2]
                rest = existing_content[header_end + 2:]
                new_content = header + entry + rest
            else:
                new_content = existing_content + entry
        else:
            # Create new changelog with header
            header = "# Community Knowledge Base Changelog\n\n"
            header += "This file tracks updates to community documentation sources.\n\n"
            header += "---\n"
            new_content = header + entry + existing_content

        with open(self.changelog_path, 'w') as f:
            f.write(new_content)

        logger.info(f"Updated changelog with {len(changes)} changes")


# =============================================================================
# ChromaDB Integration
# =============================================================================

class ChromaDBManager:
    """Manages ChromaDB operations for community docs."""

    def __init__(self):
        self.db_path = CHROMADB_PATH
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None
        self._llm = None

    def _get_client(self):
        """Lazy-load ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings
                self._client = chromadb.PersistentClient(
                    path=str(self.db_path),
                    settings=Settings(anonymized_telemetry=False)
                )
            except ImportError:
                logger.warning("ChromaDB not installed, skipping vector indexing")
                return None
        return self._client

    def _get_collection(self):
        """Get or create the collection."""
        if self._collection is None:
            client = self._get_client()
            if client:
                self._collection = client.get_or_create_collection(
                    name=COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"}
                )
        return self._collection

    def _get_llm(self):
        """Lazy-load LLM provider for embeddings."""
        if self._llm is None:
            # Check if we've already failed to initialize
            if hasattr(self, '_llm_init_failed') and self._llm_init_failed:
                return None
            try:
                sys.path.insert(0, str(PROJECT_ROOT))
                from agents.llm_provider import LLMFactory
                self._llm = LLMFactory.get_provider()
            except ImportError:
                logger.warning("LLM provider not available, skipping embeddings")
                self._llm_init_failed = True
                return None
            except Exception as e:
                logger.warning(f"Failed to initialize LLM provider: {e}")
                self._llm_init_failed = True
                return None
        return self._llm

    def backup(self) -> Optional[Path]:
        """
        Create a backup of the ChromaDB before updates.

        Returns:
            Path to backup or None if backup failed
        """
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = ARCHIVE_DIR / f"chromadb_backup_{timestamp}"

        try:
            if self.db_path.exists():
                shutil.copytree(self.db_path, backup_path)
                logger.info(f"Created ChromaDB backup at {backup_path}")
                return backup_path
        except Exception as e:
            logger.error(f"Backup failed: {e}")

        return None

    def restore(self, backup_path: Path) -> bool:
        """
        Restore ChromaDB from backup.

        Args:
            backup_path: Path to backup directory

        Returns:
            True if restore successful
        """
        try:
            if self.db_path.exists():
                shutil.rmtree(self.db_path)
            shutil.copytree(backup_path, self.db_path)
            logger.info(f"Restored ChromaDB from {backup_path}")
            # Reset connections
            self._client = None
            self._collection = None
            return True
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False

    def delete_file_embeddings(self, file_key: str) -> int:
        """
        Delete all embeddings for a specific file.

        Args:
            file_key: Unique file identifier (repo/path)

        Returns:
            Number of embeddings deleted
        """
        collection = self._get_collection()
        if not collection:
            return 0

        try:
            # Get existing IDs for this file
            results = collection.get(
                where={"file_key": file_key}
            )
            if results['ids']:
                collection.delete(ids=results['ids'])
                return len(results['ids'])
        except Exception as e:
            logger.warning(f"Error deleting embeddings for {file_key}: {e}")

        return 0

    def add_file_embeddings(
        self,
        file_key: str,
        content: str,
        metadata: FileMetadata
    ) -> int:
        """
        Add embeddings for a file.

        Args:
            file_key: Unique file identifier
            content: File content
            metadata: File metadata

        Returns:
            Number of embeddings created
        """
        collection = self._get_collection()
        llm = self._get_llm()

        if not collection or not llm:
            return 0

        # Chunk content
        chunks = self._chunk_text(content)
        if not chunks:
            return 0

        try:
            # Generate embeddings
            embeddings = llm.embed_text(chunks)

            # Prepare data for ChromaDB
            ids = [f"{file_key}_chunk_{i}" for i in range(len(chunks))]
            # Get confidence from repo config
            repo_confidence = REPO_CONFIG.get(metadata.source_repo, {}).get('confidence', 0.8)

            metadatas = [
                {
                    "file_key": file_key,
                    "source_repo": metadata.source_repo,
                    "file_path": metadata.file,
                    "commit_hash": metadata.commit_hash,
                    "chunk_id": i,
                    "source_type": "openaps_docs",
                    "confidence": repo_confidence,
                    "last_updated": metadata.last_updated
                }
                for i in range(len(chunks))
            ]

            # Add to collection
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas
            )

            return len(chunks)

        except Exception as e:
            logger.error(f"Error adding embeddings for {file_key}: {e}")
            return 0

    def _chunk_text(self, text: str) -> list[str]:
        """Chunk text into overlapping segments."""
        words = text.split()
        chunks = []

        i = 0
        while i < len(words):
            chunk_words = words[i:i + CHUNK_SIZE]
            chunk_text = " ".join(chunk_words)

            if len(chunk_text.strip()) > 100:
                chunks.append(chunk_text)

            i += (CHUNK_SIZE - CHUNK_OVERLAP)

        return chunks

    def get_collection_stats(self) -> dict:
        """Get statistics about the collection."""
        collection = self._get_collection()
        if not collection:
            return {"error": "Collection not available"}

        return {
            "name": COLLECTION_NAME,
            "count": collection.count()
        }


# =============================================================================
# Content Processor
# =============================================================================

class ContentProcessor:
    """Processes markdown content from documentation repos."""

    def __init__(self, git_manager: GitManager):
        self.git = git_manager

    def read_file(self, repo_key: str, file_path: str) -> Optional[str]:
        """Read content from a file in a repo."""
        full_path = RAW_REPOS_DIR / repo_key / file_path
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Error reading {full_path}: {e}")
            return None

    def calculate_word_count(self, content: str) -> int:
        """Calculate word count for content."""
        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', '', content)
        # Remove inline code
        text = re.sub(r'`[^`]+`', '', text)
        # Remove links
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Remove images
        text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', text)
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        words = text.split()
        return len(words)

    def calculate_content_hash(self, content: str) -> str:
        """Calculate hash of content for change detection."""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def process_file(
        self,
        repo_key: str,
        file_path: str,
        commit_hash: str,
        commit_message: str
    ) -> Optional[FileMetadata]:
        """
        Process a single file and return its metadata.

        Args:
            repo_key: Repository key
            file_path: Path to file within repo
            commit_hash: Latest commit hash for file
            commit_message: Commit message

        Returns:
            FileMetadata or None if processing failed
        """
        content = self.read_file(repo_key, file_path)
        if content is None:
            return None

        return FileMetadata(
            file=file_path,
            source_repo=repo_key,
            commit_hash=commit_hash,
            last_updated=datetime.now().isoformat(),
            commit_message=commit_message,
            word_count=self.calculate_word_count(content),
            processed_at=datetime.now().isoformat(),
            content_hash=self.calculate_content_hash(content)
        )


# =============================================================================
# Notification System
# =============================================================================

class NotificationManager:
    """Manages notifications for updates."""

    def __init__(self):
        self.notifications_file = PROJECT_ROOT / "data" / "notifications.json"
        self.notifications_file.parent.mkdir(parents=True, exist_ok=True)

    def send_summary(self, summaries: list[UpdateSummary], notify_email: bool = False) -> None:
        """
        Send update summary notification.

        Args:
            summaries: List of update summaries
            notify_email: Whether to send email notification
        """
        total_updated = sum(s.files_updated for s in summaries)
        total_new = sum(s.files_new for s in summaries)
        total_deleted = sum(s.files_deleted for s in summaries)

        message = f"{total_updated} files updated, {total_new} new, {total_deleted} deleted"
        logger.info(f"Update Summary: {message}")

        # Save to notifications file
        self._save_notification(
            title="Knowledge Base Update",
            message=message,
            details=[s.to_dict() for s in summaries]
        )

        if notify_email:
            self._send_email_notification(message, summaries)

    def _save_notification(self, title: str, message: str, details: list) -> None:
        """Save notification to file for web UI."""
        notifications = []
        if self.notifications_file.exists():
            try:
                with open(self.notifications_file, 'r') as f:
                    notifications = json.load(f)
            except:
                notifications = []

        notifications.append({
            'timestamp': datetime.now().isoformat(),
            'title': title,
            'message': message,
            'details': details,
            'read': False
        })

        # Keep last 50
        notifications = notifications[-50:]

        with open(self.notifications_file, 'w') as f:
            json.dump(notifications, f, indent=2)

    def _send_email_notification(self, message: str, summaries: list[UpdateSummary]) -> None:
        """Send email notification (stub for future implementation)."""
        # TODO: Implement email notification using smtplib or external service
        logger.info(f"Email notification would be sent: {message}")


# =============================================================================
# Main Ingestion Pipeline
# =============================================================================

class OpenAPSDocsIngestion:
    """Main orchestrator for OpenAPS documentation ingestion."""

    def __init__(self):
        self.git = GitManager()
        self.versions = VersionCache()
        self.metadata = MetadataManager()
        self.changelog = ChangelogGenerator()
        self.chromadb = ChromaDBManager()
        self.processor = ContentProcessor(self.git)
        self.notifications = NotificationManager()
        self.start_time = None

    def generate_update_log(self, summaries: list[UpdateSummary]) -> Path:
        """
        Generate a detailed update log in markdown format.

        Args:
            summaries: List of update summaries

        Returns:
            Path to the generated log file
        """
        UPDATE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_date = datetime.now().strftime('%Y-%m-%d')
        log_path = UPDATE_LOGS_DIR / f"{log_date}_changelog.md"

        content = f"""# Knowledge Base Update Log - {log_date}

Generated: {datetime.now().isoformat()}

## Summary

| Repository | Files Updated | Files New | Files Deleted | Embeddings Created |
|------------|---------------|-----------|---------------|-------------------|
"""
        for summary in summaries:
            content += f"| {summary.repo_name} | {summary.files_updated} | {summary.files_new} | {summary.files_deleted} | {summary.embeddings_created} |\n"

        total_updated = sum(s.files_updated for s in summaries)
        total_new = sum(s.files_new for s in summaries)
        total_deleted = sum(s.files_deleted for s in summaries)
        total_embeddings = sum(s.embeddings_created for s in summaries)

        content += f"| **TOTAL** | **{total_updated}** | **{total_new}** | **{total_deleted}** | **{total_embeddings}** |\n"

        # Add storage estimate
        content += "\n## Storage Estimate\n\n"
        try:
            total_size = 0
            for repo_key in REPO_CONFIG:
                repo_path = RAW_REPOS_DIR / repo_key
                if repo_path.exists():
                    size = sum(f.stat().st_size for f in repo_path.rglob('*') if f.is_file())
                    total_size += size
                    content += f"- **{repo_key}**: {size / (1024*1024):.2f} MB\n"

            # ChromaDB size
            if CHROMADB_PATH.exists():
                chroma_size = sum(f.stat().st_size for f in CHROMADB_PATH.rglob('*') if f.is_file())
                total_size += chroma_size
                content += f"- **ChromaDB**: {chroma_size / (1024*1024):.2f} MB\n"

            content += f"\n**Total storage used**: {total_size / (1024*1024):.2f} MB\n"
        except Exception as e:
            content += f"- Error calculating storage: {e}\n"

        # Add errors if any
        all_errors = []
        for summary in summaries:
            all_errors.extend(summary.errors)

        if all_errors:
            content += "\n## Errors\n\n"
            for error in all_errors:
                content += f"- {error}\n"

        # Add elapsed time if available
        if self.start_time:
            elapsed = datetime.now() - self.start_time
            content += f"\n## Timing\n\n- **Total elapsed**: {elapsed.total_seconds():.1f} seconds\n"

        with open(log_path, 'w') as f:
            f.write(content)

        logger.info(f"Generated update log: {log_path}")
        return log_path

    def clone_all(self) -> bool:
        """
        Clone all repositories for first-time setup.

        Returns:
            True if all clones successful
        """
        self.start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("Starting initial clone of all repositories")
        logger.info("=" * 60)

        success = True
        for repo_key in REPO_CONFIG:
            if not self.git.clone_repo(repo_key):
                success = False
                continue

            # Store initial commit hash
            commit = self.git.get_current_commit(repo_key)
            if commit:
                self.versions.set_commit(repo_key, commit)
                logger.info(f"Stored initial commit for {repo_key}: {commit[:8]}")

        self.versions.save()

        if success:
            logger.info("All repositories cloned successfully")
        else:
            logger.warning("Some repositories failed to clone")

        return success

    def check_for_updates(self) -> dict[str, dict]:
        """
        Check all repos for updates without pulling.

        Returns:
            Dictionary of repo_key -> update info
        """
        results = {}

        for repo_key, config in REPO_CONFIG.items():
            cached_commit = self.versions.get_commit(repo_key)
            if not cached_commit:
                results[repo_key] = {
                    'status': 'not_cloned',
                    'message': 'Repository not cloned yet'
                }
                continue

            if not self.git.fetch_updates(repo_key):
                results[repo_key] = {
                    'status': 'error',
                    'message': 'Failed to fetch updates'
                }
                continue

            remote_commit = self.git.get_remote_commit(repo_key)
            if not remote_commit:
                results[repo_key] = {
                    'status': 'error',
                    'message': 'Failed to get remote commit'
                }
                continue

            if cached_commit == remote_commit:
                results[repo_key] = {
                    'status': 'up_to_date',
                    'message': 'No updates',
                    'commit': cached_commit[:8]
                }
            else:
                # Get list of changed files
                changes = self.git.get_changed_files(repo_key, cached_commit, remote_commit)
                results[repo_key] = {
                    'status': 'updates_available',
                    'old_commit': cached_commit[:8],
                    'new_commit': remote_commit[:8],
                    'changed_files': len(changes),
                    'changes': [
                        {'file': c.file_path, 'type': c.change_type}
                        for c in changes
                    ]
                }

        return results

    def show_diff(self) -> None:
        """Show what would change if we updated."""
        updates = self.check_for_updates()

        print("\n" + "=" * 60)
        print("Repository Status")
        print("=" * 60)

        for repo_key, info in updates.items():
            config = REPO_CONFIG[repo_key]
            print(f"\n{config['display_name']} ({repo_key})")
            print("-" * 40)

            if info['status'] == 'not_cloned':
                print("  Status: NOT CLONED")
                print("  Run with --clone first")

            elif info['status'] == 'error':
                print(f"  Status: ERROR - {info['message']}")

            elif info['status'] == 'up_to_date':
                print(f"  Status: UP TO DATE")
                print(f"  Commit: {info['commit']}")

            elif info['status'] == 'updates_available':
                print(f"  Status: UPDATES AVAILABLE")
                print(f"  Current: {info['old_commit']} -> New: {info['new_commit']}")
                print(f"  Changed files: {info['changed_files']}")

                if info.get('changes'):
                    print("\n  Changes:")
                    for change in info['changes'][:20]:  # Limit display
                        symbol = {'new': '+', 'modified': 'M', 'deleted': '-'}.get(change['type'], '?')
                        print(f"    [{symbol}] {change['file']}")

                    if len(info['changes']) > 20:
                        print(f"    ... and {len(info['changes']) - 20} more")

        print("\n" + "=" * 60)

    def update_all(self, notify: bool = False, generate_log: bool = True) -> list[UpdateSummary]:
        """
        Check and process updates for all repositories.

        Args:
            notify: Whether to send notifications
            generate_log: Whether to generate changelog markdown

        Returns:
            List of UpdateSummary objects
        """
        self.start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("Starting update check for all repositories")
        logger.info("=" * 60)

        summaries = []

        for repo_key, config in REPO_CONFIG.items():
            summary = self._update_repo(repo_key)
            if summary:
                summaries.append(summary)

        # Save metadata and versions
        self.metadata.save()
        self.versions.save()

        # Generate update log
        if generate_log and any(s.files_updated + s.files_new + s.files_deleted > 0 for s in summaries):
            self.generate_update_log(summaries)

        # Send notifications
        if notify and any(s.files_updated + s.files_new + s.files_deleted > 0 for s in summaries):
            self.notifications.send_summary(summaries, notify_email=notify)

        return summaries

    def _update_repo(self, repo_key: str) -> Optional[UpdateSummary]:
        """Update a single repository."""
        config = REPO_CONFIG[repo_key]
        summary = UpdateSummary(repo_name=config['display_name'])

        cached_commit = self.versions.get_commit(repo_key)
        if not cached_commit:
            logger.info(f"Repository {repo_key} not initialized, skipping")
            return None

        # Fetch and check for updates
        if not self.git.fetch_updates(repo_key):
            summary.errors.append("Failed to fetch updates")
            summary.end_time = datetime.now()
            return summary

        remote_commit = self.git.get_remote_commit(repo_key)
        if not remote_commit:
            summary.errors.append("Failed to get remote commit")
            summary.end_time = datetime.now()
            return summary

        if cached_commit == remote_commit:
            logger.info(f"No updates for {config['display_name']}")
            summary.end_time = datetime.now()
            return summary

        logger.info(f"Updates found for {config['display_name']}: {cached_commit[:8]} -> {remote_commit[:8]}")

        # Get changed files before pulling
        changes = self.git.get_changed_files(repo_key, cached_commit, remote_commit)
        logger.info(f"Found {len(changes)} changed files")

        # Create backup before changes
        backup_path = self.chromadb.backup()

        try:
            # Pull updates
            if not self.git.pull_updates(repo_key):
                summary.errors.append("Failed to pull updates")
                if backup_path:
                    self.chromadb.restore(backup_path)
                summary.end_time = datetime.now()
                return summary

            # Process changes
            summary = self._process_changes(repo_key, changes, summary)

            # Update changelog
            self.changelog.add_update(datetime.now(), config['display_name'], changes)

            # Update cached commit
            self.versions.set_commit(repo_key, remote_commit)

        except Exception as e:
            logger.error(f"Error processing updates: {e}")
            summary.errors.append(str(e))
            if backup_path:
                logger.info("Rolling back to backup...")
                self.chromadb.restore(backup_path)

        summary.end_time = datetime.now()
        return summary

    def _process_changes(
        self,
        repo_key: str,
        changes: list[ChangeInfo],
        summary: UpdateSummary
    ) -> UpdateSummary:
        """Process changed files."""
        for change in changes:
            file_key = f"{repo_key}/{change.file_path}"

            if change.change_type == 'deleted':
                # Delete embeddings and metadata
                deleted = self.chromadb.delete_file_embeddings(file_key)
                self.metadata.delete(file_key)
                summary.files_deleted += 1
                summary.embeddings_deleted += deleted
                logger.debug(f"Deleted: {file_key} ({deleted} embeddings)")

            else:
                # Modified or new file
                # First delete old embeddings if exists
                if change.change_type == 'modified':
                    deleted = self.chromadb.delete_file_embeddings(file_key)
                    summary.embeddings_deleted += deleted
                    summary.files_updated += 1
                else:
                    summary.files_new += 1

                # Process file
                file_metadata = self.processor.process_file(
                    repo_key,
                    change.file_path,
                    change.commit_hash,
                    change.commit_message
                )

                if file_metadata:
                    # Add new embeddings
                    content = self.processor.read_file(repo_key, change.file_path)
                    if content:
                        created = self.chromadb.add_file_embeddings(
                            file_key, content, file_metadata
                        )
                        summary.embeddings_created += created

                    # Update metadata
                    self.metadata.set(file_key, file_metadata)
                    logger.debug(f"Processed: {file_key}")

        return summary

    def force_reprocess(self, notify: bool = False) -> list[UpdateSummary]:
        """
        Force re-process all files in all repositories.

        Args:
            notify: Whether to send notifications

        Returns:
            List of UpdateSummary objects
        """
        logger.info("=" * 60)
        logger.info("Force re-processing all repositories")
        logger.info("=" * 60)

        # Create backup
        backup_path = self.chromadb.backup()

        summaries = []

        try:
            for repo_key, config in REPO_CONFIG.items():
                summary = UpdateSummary(repo_name=config['display_name'])

                repo_path = RAW_REPOS_DIR / repo_key
                if not repo_path.exists():
                    logger.warning(f"Repository {repo_key} not found, skipping")
                    continue

                # Get all markdown files
                md_files = self.git.get_all_markdown_files(repo_key)
                logger.info(f"Processing {len(md_files)} files in {config['display_name']}")

                # Get current commit
                current_commit = self.git.get_current_commit(repo_key)

                # Process files in parallel
                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {}
                    for file_path in md_files:
                        file_key = f"{repo_key}/{file_path}"

                        # Get commit info for file
                        commit_info = self.git._get_file_commit_info(
                            repo_path, file_path, 'HEAD'
                        )

                        futures[executor.submit(
                            self._process_single_file,
                            repo_key, file_path, file_key, commit_info
                        )] = file_key

                    for future in as_completed(futures):
                        file_key = futures[future]
                        try:
                            file_processed, embeddings = future.result()
                            if file_processed:
                                summary.files_new += 1
                                summary.embeddings_created += embeddings
                        except Exception as e:
                            logger.error(f"Error processing {file_key}: {e}")
                            summary.errors.append(f"{file_key}: {e}")

                # Update version cache
                if current_commit:
                    self.versions.set_commit(repo_key, current_commit)

                summary.end_time = datetime.now()
                summaries.append(summary)

        except Exception as e:
            logger.error(f"Force reprocess failed: {e}")
            if backup_path:
                logger.info("Rolling back to backup...")
                self.chromadb.restore(backup_path)
            raise

        # Save metadata and versions
        self.metadata.save()
        self.versions.save()

        # Send notifications
        if notify:
            self.notifications.send_summary(summaries)

        return summaries

    def _process_single_file(
        self,
        repo_key: str,
        file_path: str,
        file_key: str,
        commit_info: dict
    ) -> tuple[bool, int]:
        """
        Process a single file and return (file_processed, embeddings_created).

        File metadata is saved regardless of embedding success.
        """
        # Delete existing embeddings (best effort)
        self.chromadb.delete_file_embeddings(file_key)

        # Process file metadata
        file_metadata = self.processor.process_file(
            repo_key,
            file_path,
            commit_info.get('hash', ''),
            commit_info.get('message', '')
        )

        if not file_metadata:
            return (False, 0)

        # Save metadata regardless of embedding success
        self.metadata.set(file_key, file_metadata)

        # Read content for embeddings
        content = self.processor.read_file(repo_key, file_path)
        if not content:
            return (True, 0)  # File processed, no embeddings

        # Try to add embeddings (may fail if no API key)
        created = self.chromadb.add_file_embeddings(file_key, content, file_metadata)

        return (True, created)

    def print_report(self, summaries: list[UpdateSummary]) -> None:
        """Print a formatted report."""
        print("\n" + "=" * 60)
        print("OpenAPS Documentation Update Report")
        print("=" * 60)

        total_updated = sum(s.files_updated for s in summaries)
        total_new = sum(s.files_new for s in summaries)
        total_deleted = sum(s.files_deleted for s in summaries)
        total_embeddings = sum(s.embeddings_created for s in summaries)
        total_errors = sum(len(s.errors) for s in summaries)

        for summary in summaries:
            print(f"\n{summary.repo_name}")
            print("-" * 40)
            print(f"  Updated:  {summary.files_updated}")
            print(f"  New:      {summary.files_new}")
            print(f"  Deleted:  {summary.files_deleted}")
            print(f"  Embeddings created: {summary.embeddings_created}")
            if summary.errors:
                print(f"  Errors:   {len(summary.errors)}")

        print("\n" + "-" * 60)
        print(f"TOTAL: {total_updated} updated, {total_new} new, {total_deleted} deleted")
        print(f"       {total_embeddings} embeddings created")
        if total_errors:
            print(f"       {total_errors} errors encountered")
        print("=" * 60)

        # Print ChromaDB stats
        stats = self.chromadb.get_collection_stats()
        print(f"\nChromaDB Collection: {stats.get('name', 'N/A')}")
        print(f"Total documents: {stats.get('count', 'N/A')}")


# =============================================================================
# CLI Interface
# =============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='OpenAPS Community Documentation Ingestion',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # First time setup - clone all repositories
  python scripts/ingest_openaps_docs.py --clone

  # Check for updates and process changes
  python scripts/ingest_openaps_docs.py --update

  # Force re-process everything
  python scripts/ingest_openaps_docs.py --force

  # Show what would change
  python scripts/ingest_openaps_docs.py --diff

  # Update with email notification
  python scripts/ingest_openaps_docs.py --update --notify
        """
    )

    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        '--clone',
        action='store_true',
        help='Clone repositories for first-time setup'
    )
    actions.add_argument(
        '--update',
        action='store_true',
        help='Check for updates and process changes'
    )
    actions.add_argument(
        '--force',
        action='store_true',
        help='Force re-process all files'
    )
    actions.add_argument(
        '--diff',
        action='store_true',
        help='Show what changed without updating'
    )
    actions.add_argument(
        '--status',
        action='store_true',
        help='Show current status and statistics'
    )

    parser.add_argument(
        '--notify',
        action='store_true',
        help='Send notification if updates found'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    return parser.parse_args()


def show_status(ingestion: OpenAPSDocsIngestion) -> None:
    """Show current status and statistics."""
    print("\n" + "=" * 60)
    print("OpenAPS Documentation Status")
    print("=" * 60)

    # Version cache
    versions = ingestion.versions.get_all()
    print("\nRepository Versions:")
    for repo_key, config in REPO_CONFIG.items():
        repo_info = versions.get(repo_key, {})
        commit = repo_info.get('commit_hash', 'Not cloned')[:8] if repo_info.get('commit_hash') else 'Not cloned'
        updated = repo_info.get('updated_at', 'Never')
        print(f"  {config['display_name']}")
        print(f"    Commit: {commit}")
        print(f"    Updated: {updated}")

    # Metadata stats
    print("\nFile Metadata:")
    for repo_key, config in REPO_CONFIG.items():
        repo_metadata = ingestion.metadata.get_by_repo(repo_key)
        print(f"  {config['display_name']}: {len(repo_metadata)} files tracked")

    # ChromaDB stats
    stats = ingestion.chromadb.get_collection_stats()
    print(f"\nChromaDB Collection: {stats.get('name', 'N/A')}")
    print(f"  Total documents: {stats.get('count', 'N/A')}")

    print("\n" + "=" * 60)


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    ingestion = OpenAPSDocsIngestion()

    try:
        if args.clone:
            success = ingestion.clone_all()
            return 0 if success else 1

        elif args.diff:
            ingestion.show_diff()
            return 0

        elif args.status:
            show_status(ingestion)
            return 0

        elif args.update:
            summaries = ingestion.update_all(notify=args.notify)
            ingestion.print_report(summaries)
            return 0 if all(len(s.errors) == 0 for s in summaries) else 1

        elif args.force:
            summaries = ingestion.force_reprocess(notify=args.notify)
            ingestion.print_report(summaries)
            return 0 if all(len(s.errors) == 0 for s in summaries) else 1

    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
