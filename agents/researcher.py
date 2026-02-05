"""
RAG Researcher Agent for Diabetes Buddy

Uses a file-based API for PDF processing and semantic search.
Provides specialist methods for each knowledge domain.
Dynamically discovers knowledge sources from knowledge-sources directory.
"""

# Force IPv4 before any Google API imports
from . import network  # noqa: F401

import os
import json
import hashlib
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Any, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from .llm_provider import LLMFactory, GenerationConfig


@dataclass
class SearchResult:
    """Represents a search result with quote, page number, and confidence."""
    quote: str
    page_number: Optional[int]
    confidence: float
    source: str
    context: str


class ResearcherAgent:
    """
    RAG Researcher Agent that searches PDF knowledge bases using the configured LLM.

    Uses a file upload API to process PDFs, with local caching
    to avoid re-uploading unchanged files.
    """

    # Legacy PDF paths removed - now using user-uploaded sources
    PDF_PATHS = {}

    # Legacy source names removed - now using user-uploaded sources
    SOURCE_NAMES = {}

    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize the researcher agent.

        Args:
            project_root: Path to the project root directory.
                         Defaults to parent of the agents/ directory.
        """
        # Get LLM provider (configured via LLM_PROVIDER env var)
        self.llm = LLMFactory.get_provider()

        # Set project root
        if project_root is None:
            project_root = Path(__file__).parent.parent
        self.project_root = Path(project_root)
        
        # Knowledge sources directory
        self.knowledge_dir = self.project_root / "docs" / "knowledge-sources"

        # Cache directory for file handles
        self.cache_dir = self.project_root / ".cache" / "llm_files"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # File handle cache (source_key -> file object)
        self._file_cache: dict[str, Any] = {}

        # Search result cache (query_hash -> results)
        self._search_cache: dict[str, list[SearchResult]] = {}
        self._cache_max_size = 100  # Limit cache size
        
        # Dynamically discovered sources
        self._discovered_sources: Optional[Dict[str, Dict]] = None

    def _discover_knowledge_sources(self) -> Dict[str, Dict]:
        """
        Dynamically discover knowledge sources from filesystem.
        Returns dict mapping source_key to source info.
        """
        sources = {}
        
        # Add legacy hardcoded sources if they exist
        for key, rel_path in self.PDF_PATHS.items():
            full_path = self.project_root / rel_path
            if full_path.exists():
                sources[key] = {
                    'path': full_path,
                    'name': self.SOURCE_NAMES.get(key, key),
                    'type': 'legacy',
                    'version': 'unknown',
                    'last_updated': None
                }
        
        # Discover new knowledge base sources
        if self.knowledge_dir.exists():
            for source_type_dir in self.knowledge_dir.iterdir():
                if not source_type_dir.is_dir():
                    continue
                    
                source_type = source_type_dir.name  # 'pump', 'cgm', 'guideline'
                
                for source_id_dir in source_type_dir.iterdir():
                    if not source_id_dir.is_dir():
                        continue
                    
                    source_id = source_id_dir.name
                    latest_dir = source_id_dir / "latest"
                    
                    if not latest_dir.exists():
                        continue
                    
                    # Load metadata
                    metadata_path = latest_dir / "metadata.json"
                    metadata = {}
                    if metadata_path.exists():
                        try:
                            with open(metadata_path) as f:
                                metadata = json.load(f)
                        except:
                            pass
                    
                    # Find PDF or repo
                    pdf_files = list(latest_dir.glob("*.pdf"))
                    is_git_repo = (latest_dir / ".git").exists()
                    
                    if pdf_files:
                        # PDF source
                        source_key = f"{source_type}_{source_id}"
                        sources[source_key] = {
                            'path': pdf_files[0],
                            'name': metadata.get('source_name', source_id.replace('_', ' ').title()),
                            'type': source_type,
                            'version': metadata.get('version', 'unknown'),
                            'last_updated': metadata.get('fetched_at'),
                            'metadata': metadata
                        }
                    elif is_git_repo:
                        # Git repo source (like OpenAPS)
                        source_key = f"{source_type}_{source_id}"
                        sources[source_key] = {
                            'path': latest_dir,
                            'name': metadata.get('source_name', source_id.replace('_', ' ').title()),
                            'type': source_type,
                            'version': metadata.get('commit', 'unknown'),
                            'last_updated': metadata.get('fetched_at'),
                            'metadata': metadata,
                            'is_git_repo': True
                        }
        
        return sources
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of a file for cache invalidation."""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def get_available_sources(self) -> List[Dict]:
        """
        Get list of all available knowledge sources.
        
        Returns:
            List of dicts with source info including staleness warnings
        """
        if self._discovered_sources is None:
            self._discovered_sources = self._discover_knowledge_sources()
        
        sources_list = []
        for source_key, source_info in self._discovered_sources.items():
            info = {
                'key': source_key,
                'name': source_info['name'],
                'type': source_info['type'],
                'version': source_info['version'],
                'last_updated': source_info.get('last_updated')
            }
            
            # Calculate staleness
            if source_info.get('last_updated'):
                try:
                    updated_date = datetime.fromisoformat(source_info['last_updated'])
                    days_old = (datetime.now() - updated_date).days
                    
                    if days_old > 365:
                        info['staleness'] = 'outdated'
                        info['staleness_warning'] = f"Knowledge source is {days_old} days old. Clinical guidelines may have changed."
                    elif days_old > 180:
                        info['staleness'] = 'stale'
                        info['staleness_warning'] = f"Knowledge source is {days_old} days old. Consider checking for updates."
                    else:
                        info['staleness'] = 'current'
                except:
                    info['staleness'] = 'unknown'
            else:
                info['staleness'] = 'unknown'
            
            sources_list.append(info)
        
        return sources_list

    def _get_search_cache_key(self, source_key: str, query: str) -> str:
        """Generate cache key for a search query."""
        # Normalize query for better cache hits
        normalized = query.lower().strip()
        cache_str = f"{source_key}:{normalized}"
        return hashlib.md5(cache_str.encode()).hexdigest()

    def _get_cache_path(self, source_key: str) -> Path:
        """Get the cache file path for a source."""
        return self.cache_dir / f"{source_key}.json"

    def _load_cached_file(self, source_key: str, file_path: Path) -> Optional[Any]:
        """
        Load a cached file handle if valid.

        Returns None if cache is invalid or expired.
        """
        cache_path = self._get_cache_path(source_key)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path) as f:
                cache_data = json.load(f)

            # Check if file hash matches
            current_hash = self._get_file_hash(file_path)
            if cache_data.get("file_hash") != current_hash:
                return None

            # Try to retrieve the file from the provider
            file_name = cache_data.get("file_name")
            if not file_name:
                return None

            file_ref = self.llm.get_file(file_id=file_name)

            # file_ref may be a FileReference wrapper; get underlying provider object
            underlying = getattr(file_ref, "provider_data", file_ref)

            # Check if file is still active
            state = getattr(underlying, "state", None)
            state_name = getattr(state, "name", None) if state else None
            if state_name == "ACTIVE":
                return file_ref

            return None

        except Exception:
            return None

    def _save_file_cache(self, source_key: str, file_path: Path, file_ref: Any) -> None:
        """Save file handle info to cache."""
        cache_path = self._get_cache_path(source_key)
        underlying = getattr(file_ref, "provider_data", None)
        file_name = getattr(underlying, "name", None) if underlying is not None else getattr(file_ref, "file_id", None)
        display_name = getattr(underlying, "display_name", None) if underlying is not None else getattr(file_ref, "display_name", None)
        cache_data = {
            "file_name": file_name,
            "file_hash": self._get_file_hash(file_path),
            "display_name": display_name,
        }
        with open(cache_path, "w") as f:
            json.dump(cache_data, f)

    def _get_or_upload_file(self, source_key: str) -> Any:
        """
        Get a file from cache or upload it to the provider.

        Args:
            source_key: Source key (e.g., 'theory', 'pump_camaps_fx', etc.)

        Returns:
            Provider file object
        """
        # Check memory cache first
        if source_key in self._file_cache:
            return self._file_cache[source_key]

        # Discover sources if not already done
        if self._discovered_sources is None:
            self._discovered_sources = self._discover_knowledge_sources()
        
        # Get source info
        if source_key not in self._discovered_sources:
            raise ValueError(f"Unknown source: {source_key}. Available: {list(self._discovered_sources.keys())}")
        
        source_info = self._discovered_sources[source_key]
        file_path = source_info['path']

        if not file_path.exists():
            raise FileNotFoundError(f"Source not found: {file_path}")
        
        # Skip git repos for now (would need special handling)
        if source_info.get('is_git_repo'):
            raise ValueError(f"Cannot upload git repository {source_key} as PDF. Use text search instead.")

        # Try to load from disk cache
        cached_file = self._load_cached_file(source_key, file_path)
        if cached_file:
            print(f"Using cached file for {source_info['name']}")
            self._file_cache[source_key] = cached_file
            return cached_file

        # Upload to provider
        print(f"Uploading {source_info['name']} for processing...")
        file_ref = self.llm.upload_file(
            file_path=file_path,
            display_name=source_info['name'],
        )

        # Cache it
        self._save_file_cache(source_key, file_path, file_ref)
        self._file_cache[source_key] = file_ref

        return file_ref

    def _search_source(self, source_key: str, query: str) -> list[SearchResult]:
        """
        Search a specific source for relevant information.

        Args:
            source_key: The source to search
            query: The search query

        Returns:
            List of SearchResult objects
        """
        # Check cache first
        cache_key = self._get_search_cache_key(source_key, query)
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]
        
        # Try to get cached context first (much faster)
        cached_context = None
        try:
            cached_context = self._get_or_create_cached_context(source_key)
        except Exception as e:
            print(f"Warning: Context cache unavailable: {e}")
        
        # Fallback to regular file handle if caching unavailable
        if not cached_context:
            try:
                file_ref = self._get_or_upload_file(source_key)
            except FileNotFoundError as e:
                print(f"Warning: {e}")
                return []
            except Exception as e:
                print(f"Error loading {source_key}: {e}")
                return []

    def _search_source(self, source_key: str, query: str) -> list[SearchResult]:
        """
        Search a specific source for relevant information.

        Args:
            source_key: The source to search
            query: The search query

        Returns:
            List of SearchResult objects
        """
        # Check cache first
        cache_key = self._get_search_cache_key(source_key, query)
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]
        
        try:
            file_ref = self._get_or_upload_file(source_key)
        except FileNotFoundError as e:
            print(f"Warning: {e}")
            return []
        except Exception as e:
            print(f"Error loading {source_key}: {e}")
            return []

        # Optimized search prompt - more concise
        search_prompt = f"""Find relevant passages for this query: "{query}"

Return JSON array with exact quotes from the document:
{{
  "results": [
    {{
      "quote": "exact text from document",
      "page_number": 42,
      "confidence": 0.95,
      "context": "why this is relevant"
    }}
  ]
}}

Rules:
- Only use text actually in the document
- Extract exact quotes (don't paraphrase)
- Include page numbers when visible
- Rate confidence 0.0-1.0
- Return empty array if nothing relevant found"""

        try:
            response_text = self.llm.generate_text(
                prompt=search_prompt,
                config=GenerationConfig(temperature=0.3),
                file_reference=file_ref,
            )

            # Handle markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            data = json.loads(response_text)

            results = []
            # Handle both list and dict responses
            items = data if isinstance(data, list) else data.get("results", [])
            
            # Get source info for version
            if self._discovered_sources is None:
                self._discovered_sources = self._discover_knowledge_sources()
            
            source_info = self._discovered_sources.get(source_key, {})
            source_name = source_info.get('name', self.SOURCE_NAMES.get(source_key, source_key))
            source_version = source_info.get('version', 'unknown')
            
            # Add version to source name if available
            if source_version and source_version != 'unknown':
                source_display = f"{source_name} (v{source_version})"
            else:
                source_display = source_name
            
            for item in items:
                results.append(SearchResult(
                    quote=item.get("quote", ""),
                    page_number=item.get("page_number"),
                    confidence=float(item.get("confidence", 0.5)),
                    source=source_display,
                    context=item.get("context", ""),
                ))

            # Cache the results (with size limit)
            if len(self._search_cache) >= self._cache_max_size:
                # Remove oldest entry (first key)
                first_key = next(iter(self._search_cache))
                del self._search_cache[first_key]
            self._search_cache[cache_key] = results

            return results

        except json.JSONDecodeError as e:
            print(f"Error parsing response from {source_key}: {e}")
            return []
        except Exception as e:
            print(f"Error searching {source_key}: {e}")
            return []
            
            for item in items:
                results.append(SearchResult(
                    quote=item.get("quote", ""),
                    page_number=item.get("page_number"),
                    confidence=float(item.get("confidence", 0.5)),
                    source=self.SOURCE_NAMES[source_key],
                    context=item.get("context", ""),
                ))

            # Cache the results (with size limit)
            if len(self._search_cache) >= self._cache_max_size:
                # Remove oldest entry (first key)
                first_key = next(iter(self._search_cache))
                del self._search_cache[first_key]
            self._search_cache[cache_key] = results

            return results

        except json.JSONDecodeError as e:
            print(f"Error parsing response from {source_key}: {e}")
            return []
        except Exception as e:
            print(f"Error searching {source_key}: {e}")
            return []

    def search_all(self, query: str) -> dict[str, list[SearchResult]]:
        """
        Search all knowledge sources for relevant information.

        Args:
            query: Search query

        Returns:
            Dictionary mapping source names to their results
        """
        # Legacy search_all - no hardcoded sources
        return {}

    def search_multiple(self, query: str, sources: list[str]) -> dict[str, list[SearchResult]]:
        """
        Search multiple knowledge sources in parallel for better performance.

        Args:
            query: Search query
            sources: List of source keys to search

        Returns:
            Dictionary mapping source names to their results
        """
        # Legacy search_multiple - no hardcoded sources
        return {}

    def format_results(self, results: list[SearchResult]) -> str:
        """Format search results as readable text."""
        if not results:
            return "No relevant information found."

        output = []
        for i, result in enumerate(results, 1):
            page_info = f" (Page {result.page_number})" if result.page_number else ""
            output.append(
                f"{i}. [{result.source}{page_info}] (Confidence: {result.confidence:.0%})\n"
                f"   \"{result.quote}\"\n"
                f"   Context: {result.context}"
            )

        return "\n\n".join(output)


if __name__ == "__main__":
    # Simple test of the researcher agent
    from dotenv import load_dotenv

    # Load environment variables
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)

    print("=" * 60)
    print("Diabetes Buddy - RAG Researcher Agent Test")
    print("=" * 60)

    try:
        researcher = ResearcherAgent()

        test_query = "How do I adjust basal rates for exercise?"
        print(f"\nTest Query: {test_query}\n")
        print("-" * 60)

        # Test each source
        sources = [
            ("Theory (Think Like a Pancreas)", researcher.search_theory),
            ("Algorithm (CamAPS FX)", researcher.search_camaps),
            ("Hardware (Ypsomed)", researcher.search_ypsomed),
            ("CGM (Libre 3)", researcher.search_libre),
        ]

        for source_name, search_func in sources:
            print(f"\n{source_name}:")
            print("-" * 40)
            results = search_func(test_query)
            print(researcher.format_results(results))

        print("\n" + "=" * 60)
        print("Test completed successfully!")
        print("=" * 60)

    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Make sure LLM_API_KEY is set in your .env file")
    except Exception as e:
        print(f"Error: {e}")
        raise
