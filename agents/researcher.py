"""
RAG Researcher Agent for Diabetes Buddy

Uses Gemini File API for PDF processing and semantic search.
Provides specialist methods for each knowledge domain.
"""

# Force IPv4 before any Google API imports
from . import network  # noqa: F401

import os
import json
import hashlib
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from google import genai
from google.genai import types


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
    RAG Researcher Agent that searches PDF knowledge bases using Gemini.

    Uses the Gemini File API to upload and process PDFs, with local caching
    to avoid re-uploading unchanged files.
    """

    # PDF file paths relative to project root
    PDF_PATHS = {
        "theory": "docs/theory/Think-Like-a-Pancreas-A-Practical-Guide-to-Managing-Gary-Scheiner-MS-Cdces-Revised-2025-Hachette-Go-9780306837159-ce3facbbce8e750f2d5875907dcab753-Annas-Archive.pdf",
        "camaps": "docs/manuals/algorithm/user_manual_fx_mmoll_commercial_ca.pdf",
        "ypsomed": "docs/manuals/hardware/YPU_eIFU_REF_700009424_UK-en_V01.pdf",
        "libre": "docs/manuals/hardware/ART41641-001_rev-A-web.pdf",
    }

    # Human-readable source names
    SOURCE_NAMES = {
        "theory": "Think Like a Pancreas",
        "camaps": "CamAPS FX User Manual",
        "ypsomed": "Ypsomed Pump Manual",
        "libre": "FreeStyle Libre 3 Manual",
    }

    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize the researcher agent.

        Args:
            project_root: Path to the project root directory.
                         Defaults to parent of the agents/ directory.
        """
        # Configure API key
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        # Initialize the Gemini client
        self.client = genai.Client(api_key=api_key)

        # Set project root
        if project_root is None:
            project_root = Path(__file__).parent.parent
        self.project_root = Path(project_root)

        # Cache directory for file handles
        self.cache_dir = self.project_root / ".cache" / "gemini_files"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # File handle cache (source_key -> file object)
        self._file_cache: dict[str, types.File] = {}

        # Search result cache (query_hash -> results)
        self._search_cache: dict[str, list[SearchResult]] = {}
        self._cache_max_size = 100  # Limit cache size

        # Model to use
        self.model_name = "gemini-2.5-flash"

    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of a file for cache invalidation."""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _get_search_cache_key(self, source_key: str, query: str) -> str:
        """Generate cache key for a search query."""
        # Normalize query for better cache hits
        normalized = query.lower().strip()
        cache_str = f"{source_key}:{normalized}"
        return hashlib.md5(cache_str.encode()).hexdigest()

    def _get_cache_path(self, source_key: str) -> Path:
        """Get the cache file path for a source."""
        return self.cache_dir / f"{source_key}.json"

    def _load_cached_file(self, source_key: str, file_path: Path) -> Optional[types.File]:
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

            # Try to retrieve the file from Gemini
            file_name = cache_data.get("file_name")
            if not file_name:
                return None

            gemini_file = self.client.files.get(name=file_name)

            # Check if file is still active
            if gemini_file.state.name == "ACTIVE":
                return gemini_file

            return None

        except Exception:
            return None

    def _save_file_cache(self, source_key: str, file_path: Path, gemini_file: types.File) -> None:
        """Save file handle info to cache."""
        cache_path = self._get_cache_path(source_key)
        cache_data = {
            "file_name": gemini_file.name,
            "file_hash": self._get_file_hash(file_path),
            "display_name": gemini_file.display_name,
        }
        with open(cache_path, "w") as f:
            json.dump(cache_data, f)

    def _get_or_upload_file(self, source_key: str) -> types.File:
        """
        Get a file from cache or upload it to Gemini.

        Args:
            source_key: One of 'theory', 'camaps', 'ypsomed', 'libre'

        Returns:
            Gemini File object
        """
        # Check memory cache first
        if source_key in self._file_cache:
            return self._file_cache[source_key]

        # Get file path
        if source_key not in self.PDF_PATHS:
            raise ValueError(f"Unknown source: {source_key}")

        file_path = self.project_root / self.PDF_PATHS[source_key]

        if not file_path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path}")

        # Try to load from disk cache
        cached_file = self._load_cached_file(source_key, file_path)
        if cached_file:
            print(f"Using cached file for {self.SOURCE_NAMES[source_key]}")
            self._file_cache[source_key] = cached_file
            return cached_file

        # Upload to Gemini
        print(f"Uploading {self.SOURCE_NAMES[source_key]} to Gemini...")
        gemini_file = self.client.files.upload(
            file=str(file_path),
            config=types.UploadFileConfig(
                display_name=self.SOURCE_NAMES[source_key],
            ),
        )

        # Wait for processing
        while gemini_file.state.name == "PROCESSING":
            print(f"  Processing {self.SOURCE_NAMES[source_key]}...")
            time.sleep(2)
            gemini_file = self.client.files.get(name=gemini_file.name)

        if gemini_file.state.name != "ACTIVE":
            raise RuntimeError(f"File processing failed: {gemini_file.state.name}")

        print(f"  {self.SOURCE_NAMES[source_key]} ready!")

        # Cache it
        self._save_file_cache(source_key, file_path, gemini_file)
        self._file_cache[source_key] = gemini_file

        return gemini_file

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
                gemini_file = self._get_or_upload_file(source_key)
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
            gemini_file = self._get_or_upload_file(source_key)
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
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[gemini_file, search_prompt],
            )

            # Parse the JSON response
            response_text = response.text.strip()

            # Handle markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            data = json.loads(response_text)

            results = []
            # Handle both list and dict responses
            items = data if isinstance(data, list) else data.get("results", [])
            
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

    def search_theory(self, query: str) -> list[SearchResult]:
        """
        Search Think Like a Pancreas for diabetes management theory.

        Args:
            query: Search query about diabetes theory, insulin strategies,
                   carb counting, etc.

        Returns:
            List of SearchResult objects with exact quotes
        """
        return self._search_source("theory", query)

    def search_camaps(self, query: str) -> list[SearchResult]:
        """
        Search CamAPS FX manual for hybrid closed-loop algorithm information.

        Args:
            query: Search query about CamAPS FX settings, algorithm behavior,
                   boost/ease modes, etc.

        Returns:
            List of SearchResult objects with exact quotes
        """
        return self._search_source("camaps", query)

    def search_ypsomed(self, query: str) -> list[SearchResult]:
        """
        Search Ypsomed pump manual for hardware procedures.

        Args:
            query: Search query about pump operation, cartridge changes,
                   infusion sets, troubleshooting, etc.

        Returns:
            List of SearchResult objects with exact quotes
        """
        return self._search_source("ypsomed", query)

    def search_libre(self, query: str) -> list[SearchResult]:
        """
        Search FreeStyle Libre 3 manual for CGM information.

        Args:
            query: Search query about sensor application, readings,
                   alarms, troubleshooting, etc.

        Returns:
            List of SearchResult objects with exact quotes
        """
        return self._search_source("libre", query)

    def search_all(self, query: str) -> dict[str, list[SearchResult]]:
        """
        Search all knowledge sources for relevant information.

        Args:
            query: Search query

        Returns:
            Dictionary mapping source names to their results
        """
        return {
            "theory": self.search_theory(query),
            "camaps": self.search_camaps(query),
            "ypsomed": self.search_ypsomed(query),
            "libre": self.search_libre(query),
        }

    def search_multiple(self, query: str, sources: list[str]) -> dict[str, list[SearchResult]]:
        """
        Search multiple knowledge sources in parallel for better performance.

        Args:
            query: Search query
            sources: List of source keys to search (e.g., ['theory', 'camaps'])

        Returns:
            Dictionary mapping source names to their results
        """
        results = {}
        
        # Map source keys to search functions
        search_map = {
            "theory": self.search_theory,
            "camaps": self.search_camaps,
            "ypsomed": self.search_ypsomed,
            "libre": self.search_libre,
        }
        
        # Execute searches in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_source = {
                executor.submit(search_map[source], query): source
                for source in sources
                if source in search_map
            }
            
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    results[source] = future.result()
                except Exception as e:
                    print(f"Error searching {source}: {e}")
                    results[source] = []
        
        return results

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
        print("Make sure GEMINI_API_KEY is set in your .env file")
    except Exception as e:
        print(f"Error: {e}")
        raise
