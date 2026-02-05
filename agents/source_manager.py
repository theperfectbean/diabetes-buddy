"""
User Source Manager for Diabetes Buddy

Manages user-uploaded PDFs and their integration into the ChromaDB knowledge base.
"""

import os
import re
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

# Device name pattern mapping - converts filenames/collection names to clean device names
# Patterns are checked in order; first match wins
DEVICE_NAME_PATTERNS = [
    # CamAPS FX - various filename patterns (including internal doc codes like Art46090)
    (r"camaps|cam.*aps|fx.*mmoll|manual.*fx|mmoll.*commercial|art46090", "CamAPS FX"),
    # Omnipod 5
    (r"omnipod.*5|op5|dash.*5", "Omnipod 5"),
    # Omnipod DASH
    (r"omnipod.*dash|dash.*pump", "Omnipod DASH"),
    # Tandem Control-IQ
    (r"control.*iq|tandem.*iq|t.*slim.*x2|tslim", "Tandem Control-IQ"),
    # Medtronic 780G
    (r"780g|medtronic.*780|guardian.*4", "Medtronic 780G"),
    # Medtronic 770G
    (r"770g|medtronic.*770", "Medtronic 770G"),
    # iLet Bionic Pancreas
    (r"ilet|bionic.*pancreas", "iLet Bionic Pancreas"),
    # Dexcom G7
    (r"dexcom.*g7|g7.*cgm", "Dexcom G7"),
    # Dexcom G6
    (r"dexcom.*g6|g6.*cgm", "Dexcom G6"),
    # FreeStyle Libre 3
    (r"libre.*3|freestyle.*3", "FreeStyle Libre 3"),
    # FreeStyle Libre 2
    (r"libre.*2|freestyle.*2", "FreeStyle Libre 2"),
    # FreeStyle Libre (original)
    (r"freestyle.*libre|libre(?!.*[23])", "FreeStyle Libre"),
    # Guardian Sensor
    (r"guardian.*sensor|guardian.*cgm", "Medtronic Guardian"),
    # YpsoPump
    (r"ypsopump|ypso|mylife.*ypso", "YpsoPump"),
    # Loop (DIY)
    (r"loop.*app|loopkit", "Loop (DIY)"),
    # AndroidAPS (DIY)
    (r"android.*aps|aaps", "AndroidAPS (DIY)"),
    # OpenAPS (DIY)
    (r"openaps|oref", "OpenAPS (DIY)"),
]


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
    indexed_at: Optional[str] = None


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
        """Generate human-readable display name using pattern matching."""
        name = Path(filename).stem
        name_lower = name.lower()

        # Try to match against known device patterns
        for pattern, clean_name in DEVICE_NAME_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                return clean_name

        # Fallback: clean up the filename
        name = name.replace('_', ' ').replace('-', ' ')
        # Remove common noise words from PDF filenames
        noise_words = ['manual', 'user', 'guide', 'rev', 'commercial', 'mmoll', 'mgdl', 'eifu', 'ifu']
        words = name.split()
        cleaned_words = [w for w in words if w.lower() not in noise_words and not re.match(r'^[a-z]?\d+$', w.lower())]
        if cleaned_words:
            return ' '.join(cleaned_words).title()
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

    def get_user_devices(self) -> List[Dict[str, str]]:
        """
        Detect user-uploaded device documentation.

        Returns:
            List of dicts with keys:
            - name: Human-readable device name (e.g., "CamAPS FX")
            - type: "algorithm" | "pump" | "cgm" | "unknown"
            - collection: ChromaDB collection name (e.g., "user_camaps_fx")
        """
        user_devices: List[Dict[str, str]] = []
        seen_names = set()  # Deduplicate by clean name

        # Method 1: Scan docs/user-sources/ directory (only include actual device manuals)
        if self.sources_dir.exists():
            for path in self.sources_dir.glob("**/*.pdf"):
                # Use pattern matching for clean device name
                device_name = self._generate_display_name(path.name)
                
                # Skip non-device documents (clinical guidelines, standards)
                skip_patterns = ['standards', 'guidelines', 'ada', 'protocol', 'clinical']
                if any(skip in device_name.lower() for skip in skip_patterns):
                    continue
                    
                if device_name in seen_names:
                    continue
                seen_names.add(device_name)

                collection_name = f"user_{path.stem.lower().replace('-', '_').replace(' ', '_')}"
                device_type = self._detect_device_type(device_name)
                
                # Only add if it's an actual device (not unknown type)
                if device_type != "unknown":
                    user_devices.append({
                        "name": device_name,
                        "type": device_type,
                        "collection": collection_name
                    })

        # Method 2: Query ChromaDB for ALL device collections (not just user-prefixed)
        try:
            chromadb_path = self.project_root / ".cache" / "chromadb"
            client = chromadb.PersistentClient(
                path=str(chromadb_path),
                settings=Settings(anonymized_telemetry=False)
            )
            collections = client.list_collections()
            for coll in collections:
                # Check if collection matches any device pattern
                coll_name_lower = coll.name.lower()
                device_name = None
                
                # Try to match against device patterns
                for pattern, clean_name in DEVICE_NAME_PATTERNS:
                    if re.search(pattern, coll_name_lower, re.IGNORECASE):
                        device_name = clean_name
                        break
                
                # If matched and not already seen, add it
                if device_name and device_name not in seen_names:
                    seen_names.add(device_name)
                    if not any(d["collection"] == coll.name for d in user_devices):
                        user_devices.append({
                            "name": device_name,
                            "type": self._detect_device_type(device_name),
                            "collection": coll.name
                        })
                        logger.info(f"Detected device collection: {coll.name} -> {device_name}")
        except Exception as e:
            logger.warning(f"Could not query ChromaDB for user collections: {e}")

        return user_devices

    def _match_device_pattern(self, name: str) -> str:
        """Match a name against device patterns and return clean device name."""
        name_lower = name.lower()

        # Try to match against known device patterns
        for pattern, clean_name in DEVICE_NAME_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                return clean_name

        # Fallback: clean up the name
        name = name.replace('_', ' ').replace('-', ' ')
        # Remove common noise words
        noise_words = ['manual', 'user', 'guide', 'rev', 'commercial', 'mmoll', 'mgdl', 'eifu', 'ifu']
        words = name.split()
        cleaned_words = [w for w in words if w.lower() not in noise_words and not re.match(r'^[a-z]?\d+$', w.lower())]
        if cleaned_words:
            return ' '.join(cleaned_words).title()
        return name.title()

    def _detect_device_type(self, name: str) -> str:
        """Classify device type based on name keywords."""
        name_lower = name.lower()

        # Algorithm/closed-loop systems
        if any(kw in name_lower for kw in [
            "camaps",
            "omnipod 5",
            "control-iq",
            "medtronic 780g",
            "ilet"
        ]):
            return "algorithm"

        # Pumps
        if any(kw in name_lower for kw in [
            "pump",
            "omnipod",
            "tandem",
            "medtronic",
            "ypsopump"
        ]):
            return "pump"

        # CGMs
        if any(kw in name_lower for kw in [
            "dexcom",
            "libre",
            "guardian",
            "cgm",
            "sensor"
        ]):
            return "cgm"

        return "unknown"