"""
ChromaDB-based RAG Researcher Agent for Diabetes Buddy

Fast local vector search replacing slow Gemini File API calls.
One-time PDF processing (~3min), then <5s queries forever.
"""

# Force IPv4 before any Google API imports
from . import network  # noqa: F401

import os
import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
import hashlib

import chromadb
from chromadb.config import Settings
from .llm_provider import LLMFactory, GenerationConfig
import PyPDF2


@dataclass
class SearchResult:
    """Represents a search result with quote, page number, and confidence."""
    quote: str
    page_number: Optional[int]
    confidence: float
    source: str
    context: str


class ChromaDBBackend:
    """
    ChromaDB-based research backend with local vector search.
    
    Processes PDFs once, stores embeddings locally, then performs
    fast semantic search without repeated Gemini API calls.
    """

    # PDF file paths relative to project root
    PDF_PATHS = {
        "theory": "docs/theory/Think-Like-a-Pancreas-A-Practical-Guide-to-Managing-Gary-Scheiner-MS-Cdces-Revised-2025-Hachette-Go-9780306837159-ce3facbbce8e750f2d5875907dcab753-Annas-Archive.pdf",
        "camaps": "docs/manuals/algorithm/user_manual_fx_mmoll_commercial_ca.pdf",
        "ypsomed": "docs/manuals/hardware/YPU_eIFU_REF_700009424_UK-en_V01.pdf",
        "libre": "docs/manuals/hardware/ART41641-001_rev-A-web.pdf",
        "ada_standards": "docs/theory/ADA-Standards-of-Care-2026.pdf",
        "australian_guidelines": "docs/theory/Australian-Diabetes-Guidelines.pdf",
    }

    # Human-readable source names
    SOURCE_NAMES = {
        "theory": "Think Like a Pancreas",
        "camaps": "CamAPS FX User Manual",
        "ypsomed": "Ypsomed Pump Manual",
        "libre": "FreeStyle Libre 3 Manual",
        "ada_standards": "ADA Standards of Care 2026",
        "australian_guidelines": "Australian Diabetes Guidelines",
    }

    # Chunking parameters
    CHUNK_SIZE = 500  # words
    CHUNK_OVERLAP = 100  # words
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize ChromaDB backend.
        
        Args:
            project_root: Path to project root directory
        """
        # Get LLM provider (configured via LLM_PROVIDER env var)
        self.llm = LLMFactory.get_provider()
        # Expose configured embedding model for diagnostics and downstream code
        try:
            self.embedding_model = getattr(self.llm, "embedding_model", None) or (self.llm.get_model_info().model_name if hasattr(self.llm, 'get_model_info') else None)
        except Exception:
            self.embedding_model = None
        
        # Set project root
        if project_root is None:
            project_root = Path(__file__).parent.parent
        self.project_root = Path(project_root)
        
        # Initialize ChromaDB
        self.db_path = self.project_root / ".cache" / "chromadb"
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Initialize collections (creates if needed)
        self._init_collections()
    
    def _init_collections(self):
        """Initialize or load ChromaDB collections for each source."""
        for source_key in self.PDF_PATHS.keys():
            collection = self.chroma_client.get_or_create_collection(
                name=source_key,
                metadata={"hnsw:space": "cosine"}
            )
            
            # Check if collection is empty (needs processing)
            if collection.count() == 0:
                pdf_path = self.project_root / self.PDF_PATHS[source_key]
                if pdf_path.exists():
                    print(f"🔧 Processing {self.SOURCE_NAMES[source_key]} for first time...")
                    self._process_pdf(source_key, pdf_path, collection)
                    print(f"✅ {self.SOURCE_NAMES[source_key]} ready!")
                else:
                    print(f"⚠️  Warning: PDF not found: {pdf_path}")
    
    def _extract_text_from_pdf(self, pdf_path: Path) -> List[tuple[str, int]]:
        """
        Extract text from PDF with page numbers.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of (text, page_number) tuples
        """
        pages = []
        try:
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page_num, page in enumerate(reader.pages, start=1):
                    text = page.extract_text()
                    if text.strip():
                        pages.append((text, page_num))
        except Exception as e:
            print(f"Error extracting PDF text: {e}")
        
        return pages
    
    def _chunk_text(self, text: str, page_num: int) -> List[tuple[str, int]]:
        """
        Chunk text into overlapping segments.
        
        Args:
            text: Text to chunk
            page_num: Page number for metadata
            
        Returns:
            List of (chunk_text, page_num) tuples
        """
        words = text.split()
        chunks = []
        
        i = 0
        while i < len(words):
            chunk_words = words[i:i + self.CHUNK_SIZE]
            chunk_text = " ".join(chunk_words)
            
            # Only keep chunks with meaningful content
            if len(chunk_text.strip()) > 100:
                chunks.append((chunk_text, page_num))
            
            # Move forward by (CHUNK_SIZE - CHUNK_OVERLAP)
            i += (self.CHUNK_SIZE - self.CHUNK_OVERLAP)
        
        return chunks
    
    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of texts using Gemini.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        try:
            return self.llm.embed_text(texts)
        except Exception as e:
            print(f"Error embedding batch: {e}")
            # Retry with smaller batch on failure
            if len(texts) > 1:
                mid = len(texts) // 2
                return self._embed_batch(texts[:mid]) + self._embed_batch(texts[mid:])
            return [[0.0] * 768]  # Return zero vector as fallback
    
    def _process_pdf(self, source_key: str, pdf_path: Path, collection):
        """
        Process a PDF: extract, chunk, embed, and store in ChromaDB.
        
        Args:
            source_key: Source identifier
            pdf_path: Path to PDF file
            collection: ChromaDB collection to store in
        """
        # Extract text from PDF
        print(f"   📄 Extracting text...")
        pages = self._extract_text_from_pdf(pdf_path)
        
        if not pages:
            print(f"   ⚠️  No text extracted from PDF")
            return
        
        # Chunk all pages
        print(f"   ✂️  Chunking {len(pages)} pages...")
        all_chunks = []
        for text, page_num in pages:
            chunks = self._chunk_text(text, page_num)
            all_chunks.extend(chunks)
        
        print(f"   📦 Created {len(all_chunks)} chunks")
        
        if not all_chunks:
            return
        
        # Embed in batches
        print(f"   🧠 Embedding chunks...")
        batch_size = 10
        all_embeddings = []
        
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]
            batch_texts = [chunk[0] for chunk in batch]
            embeddings = self._embed_batch(batch_texts)
            all_embeddings.extend(embeddings)
            
            # Show progress
            progress = min(i + batch_size, len(all_chunks))
            print(f"      {progress}/{len(all_chunks)} chunks embedded", end="\r")
            
            # Rate limiting
            time.sleep(0.5)
        
        print(f"      {len(all_chunks)}/{len(all_chunks)} chunks embedded ✓")
        
        # Store in ChromaDB
        print(f"   💾 Storing in ChromaDB...")
        ids = [f"{source_key}_{i}" for i in range(len(all_chunks))]
        documents = [chunk[0] for chunk in all_chunks]
        metadatas = [
            {
                "source": source_key,
                "source_name": self.SOURCE_NAMES[source_key],
                "page": chunk[1],
                "chunk_id": i
            }
            for i, chunk in enumerate(all_chunks)
        ]
        
        collection.add(
            ids=ids,
            embeddings=all_embeddings,
            documents=documents,
            metadatas=metadatas
        )
    
    def _search_collection(self, source_key: str, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Search a ChromaDB collection for relevant chunks.
        
        Args:
            source_key: Source collection to search
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of SearchResult objects
        """
        try:
            collection = self.chroma_client.get_collection(name=source_key)
        except Exception as e:
            print(f"Warning: Collection '{source_key}' not found: {e}")
            return []
        
        if collection.count() == 0:
            return []
        
        # Embed query
        try:
            query_embedding = self.llm.embed_text(query)
        except Exception as e:
            print(f"Error embedding query: {e}")
            return []
        
        # Search ChromaDB
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count())
            )
        except Exception as e:
            print(f"Error querying collection: {e}")
            return []
        
        # Convert to SearchResult objects
        search_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i] if results['distances'] else 0.5
                
                # Convert distance to confidence (cosine similarity)
                # Distance is 0-2 for cosine, convert to 0-1 confidence
                confidence = 1.0 - (distance / 2.0)
                
                search_results.append(SearchResult(
                    quote=doc,
                    page_number=metadata.get('page'),
                    confidence=confidence,
                    source=self.SOURCE_NAMES[source_key],
                    context=f"Retrieved from {self.SOURCE_NAMES[source_key]}"
                ))
        
        return search_results
    
    def _synthesize_with_gemini(self, query: str, chunks: List[SearchResult]) -> str:
        """
        Synthesize an answer using Gemini with retrieved chunks.
        
        Args:
            query: User's question
            chunks: Retrieved context chunks
            
        Returns:
            Synthesized answer
        """
        if not chunks:
            return "No relevant information found in the knowledge base for this query."
        
        # Build context from chunks
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            page_info = f", Page {chunk.page_number}" if chunk.page_number else ""
            context_parts.append(
                f"[Context {i}] ({chunk.source}{page_info}):\n{chunk.quote}\n"
            )
        
        context = "\n".join(context_parts)
        
        prompt = f"""Answer the user's question using ONLY the provided context excerpts from diabetes management resources.

Context:
{context}

User Question: {query}

Instructions:
1. Provide a clear, helpful answer based on the context
2. Include direct quotes when relevant
3. Cite sources with page numbers
4. If the context doesn't fully answer the question, acknowledge limitations
5. Do NOT provide specific insulin doses or medical advice

Your answer:"""

        try:
            return self.llm.generate_text(
                prompt=prompt,
                config=GenerationConfig(temperature=0.7),
            )
        except Exception as e:
            print(f"Error generating answer: {e}")
            # Fallback to formatted chunks
            return "\n\n".join([
                f"{chunk.quote} ({chunk.source}, Page {chunk.page_number})"
                for chunk in chunks
            ])
    
    def search_theory(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Search Think Like a Pancreas."""
        chunks = self._search_collection("theory", query, top_k)
        return chunks
    
    def search_camaps(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Search CamAPS FX manual."""
        chunks = self._search_collection("camaps", query, top_k)
        return chunks
    
    def search_ypsomed(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Search Ypsomed pump manual."""
        chunks = self._search_collection("ypsomed", query, top_k)
        return chunks
    
    def search_libre(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Search FreeStyle Libre 3 manual."""
        chunks = self._search_collection("libre", query, top_k)
        return chunks

    def search_ada_standards(self, query: str, sections: List[str] = None, top_k: int = 5) -> List[SearchResult]:
        """
        Search ADA Standards of Care 2026.

        Args:
            query: Search query
            sections: Optional list of section numbers to focus on (e.g., ["6", "10", "11", "12"])
                     - Section 6: Glycemic Goals and Hypoglycemia
                     - Section 7: Diabetes Technology
                     - Section 10: Cardiovascular Disease
                     - Section 11: Chronic Kidney Disease
                     - Section 12: Retinopathy, Neuropathy, and Foot Care
            top_k: Number of results to return

        Returns:
            List of SearchResult objects
        """
        # Enhance query with section context if specified
        if sections:
            section_context = f" (focusing on Sections {', '.join(sections)})"
            enhanced_query = query + section_context
        else:
            enhanced_query = query

        chunks = self._search_collection("ada_standards", enhanced_query, top_k)
        return chunks

    def search(self, query: str, top_k: int = 5) -> dict:
        """
        General search across all configured sources.

        Returns a mapping of source_key -> list[SearchResult].
        """
        results = {}
        for source_key in self.PDF_PATHS.keys():
            method_name = f"search_{source_key}"
            if hasattr(self, method_name):
                try:
                    fn = getattr(self, method_name)
                    results[source_key] = fn(query, top_k=top_k)
                except Exception:
                    results[source_key] = []
            else:
                # fallback to collection search
                try:
                    results[source_key] = self._search_collection(source_key, query, top_k)
                except Exception:
                    results[source_key] = []

        return results

    def search_australian_guidelines(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Search Australian Diabetes Guidelines.

        Particularly valuable for:
        - Technology recommendations (Sections 3.1-3.3)
        - Hybrid closed-loop system evidence
        - CGM and pump therapy evidence

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of SearchResult objects
        """
        chunks = self._search_collection("australian_guidelines", query, top_k)
        return chunks

    def search_clinical_guidelines(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Search both ADA Standards and Australian Guidelines.

        Args:
            query: Search query
            top_k: Number of results per source

        Returns:
            Combined list of SearchResult objects from both sources
        """
        ada_results = self._search_collection("ada_standards", query, top_k)
        aus_results = self._search_collection("australian_guidelines", query, top_k)

        # Combine and sort by confidence
        combined = ada_results + aus_results
        combined.sort(key=lambda x: x.confidence, reverse=True)
        return combined[:top_k * 2]  # Return up to 2x top_k results

    def search_research_papers(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Search PubMed research papers ingested into the knowledge base.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of SearchResult objects from research papers
        """
        try:
            collection = self.chroma_client.get_collection(name="pubmed_research")
        except Exception:
            # Collection doesn't exist yet (no papers ingested)
            return []

        if collection.count() == 0:
            return []

        # Embed query
        try:
            query_embedding = self.llm.embed_text(query)
        except Exception as e:
            print(f"Error embedding query: {e}")
            return []

        # Search ChromaDB
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count())
            )
        except Exception as e:
            print(f"Error querying research papers collection: {e}")
            return []

        # Convert to SearchResult objects
        search_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i] if results['distances'] else 0.5

                # Convert distance to confidence
                confidence = 1.0 - (distance / 2.0)

                search_results.append(SearchResult(
                    quote=doc,
                    page_number=None,
                    confidence=confidence,
                    source="PubMed Research Paper",
                    context=f"Retrieved from {metadata.get('document_id', 'unknown')}"
                ))

        return search_results

    def search_openaps_docs(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Search OpenAPS community documentation (OpenAPS, AndroidAPS, Loop).

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of SearchResult objects from community docs
        """
        try:
            collection = self.chroma_client.get_collection(name="openaps_docs")
        except Exception:
            # Collection doesn't exist yet
            return []

        if collection.count() == 0:
            return []

        # Embed query
        try:
            query_embedding = self.llm.embed_text(query)
        except Exception as e:
            print(f"Error embedding query: {e}")
            return []

        # Search ChromaDB
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count())
            )
        except Exception as e:
            print(f"Error querying openaps_docs collection: {e}")
            return []

        # Convert to SearchResult objects
        search_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i] if results['distances'] else 0.5

                # Convert distance to confidence
                confidence = metadata.get('confidence', 1.0 - (distance / 2.0))

                search_results.append(SearchResult(
                    quote=doc,
                    page_number=None,
                    confidence=confidence,
                    source=f"OpenAPS Docs ({metadata.get('source_repo', 'unknown')})",
                    context=metadata.get('file_path', '')
                ))

        return search_results

    def search_all_collections(
        self,
        query: str,
        top_k: int = 5,
        deduplicate: bool = True,
        similarity_threshold: float = 0.9
    ) -> List[SearchResult]:
        """
        Search ALL collections and return merged, deduplicated results.

        Args:
            query: Search query
            top_k: Number of results to return per collection
            deduplicate: Whether to remove near-duplicate results
            similarity_threshold: Cosine similarity threshold for deduplication

        Returns:
            List of SearchResult objects sorted by confidence
        """
        import logging
        from concurrent.futures import ThreadPoolExecutor, as_completed

        logger = logging.getLogger(__name__)

        # All available search methods and their collection names
        search_methods = {
            'theory': self.search_theory,
            'camaps': self.search_camaps,
            'ypsomed': self.search_ypsomed,
            'libre': self.search_libre,
            'ada_standards': self.search_ada_standards,
            'australian_guidelines': self.search_australian_guidelines,
            'research_papers': self.search_research_papers,
            'openaps_docs': self.search_openaps_docs,
        }

        all_results = []
        search_times = {}

        # Search all collections in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_collection = {}
            for name, search_fn in search_methods.items():
                future_to_collection[executor.submit(
                    self._timed_search, search_fn, query, top_k
                )] = name

            for future in as_completed(future_to_collection):
                collection_name = future_to_collection[future]
                try:
                    results, elapsed = future.result()
                    search_times[collection_name] = elapsed
                    all_results.extend(results)
                    logger.debug(f"Collection '{collection_name}': {len(results)} results in {elapsed:.3f}s")
                except Exception as e:
                    logger.warning(f"Error searching collection '{collection_name}': {e}")

        # Log performance
        total_time = sum(search_times.values())
        logger.info(f"Multi-collection search: {len(all_results)} total results in {total_time:.3f}s")

        # Sort by confidence
        all_results.sort(key=lambda x: x.confidence, reverse=True)

        # Deduplicate by content similarity
        if deduplicate and len(all_results) > 1:
            all_results = self._deduplicate_results(all_results, similarity_threshold)
            logger.debug(f"After deduplication: {len(all_results)} results")

        # Return top results
        return all_results[:top_k]

    def _timed_search(self, search_fn, query: str, top_k: int) -> tuple:
        """Execute a search function and return (results, elapsed_time)."""
        start = time.time()
        try:
            results = search_fn(query, top_k=top_k)
        except TypeError:
            # Some search methods don't accept top_k
            results = search_fn(query)
        elapsed = time.time() - start
        return results, elapsed

    def _deduplicate_results(
        self,
        results: List[SearchResult],
        similarity_threshold: float = 0.9
    ) -> List[SearchResult]:
        """
        Remove near-duplicate results based on content similarity.

        Args:
            results: List of SearchResult objects
            similarity_threshold: Cosine similarity threshold (0.9 = 90% similar)

        Returns:
            Deduplicated list of SearchResult objects
        """
        if len(results) <= 1:
            return results

        # Get embeddings for all results
        try:
            texts = [r.quote[:500] for r in results]  # Use first 500 chars
            embeddings = self.llm.embed_text(texts)
        except Exception:
            # If embedding fails, return original results
            return results

        # Calculate cosine similarity and filter duplicates
        import numpy as np

        embeddings_array = np.array(embeddings)
        norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
        normalized = embeddings_array / (norms + 1e-10)

        # Keep track of which results to keep
        keep_indices = [0]  # Always keep the first (highest confidence)

        for i in range(1, len(results)):
            is_duplicate = False
            for j in keep_indices:
                similarity = np.dot(normalized[i], normalized[j])
                if similarity >= similarity_threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                keep_indices.append(i)

        return [results[i] for i in keep_indices]

    @staticmethod
    def format_citation(result: SearchResult) -> str:
        """
        Format a search result with source attribution and confidence.

        Args:
            result: SearchResult object

        Returns:
            Formatted string like "[Source: OpenAPS Docs | Confidence: 0.80]"
        """
        return f"[Source: {result.source} | Confidence: {result.confidence:.2f}]"

    def search_with_citations(
        self,
        query: str,
        top_k: int = 5
    ) -> List[dict]:
        """
        Search all collections and return results with formatted citations.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of dicts with 'content', 'citation', and 'metadata'
        """
        results = self.search_all_collections(query, top_k=top_k)

        return [
            {
                'content': result.quote,
                'citation': self.format_citation(result),
                'metadata': {
                    'source': result.source,
                    'confidence': result.confidence,
                    'page': result.page_number,
                    'context': result.context
                }
            }
            for result in results
        ]

    def get_collection_stats(self) -> dict:
        """Get statistics for all ChromaDB collections."""
        stats = {}
        try:
            for collection in self.chroma_client.list_collections():
                stats[collection.name] = {
                    'count': collection.count(),
                    'metadata': collection.metadata
                }
        except Exception as e:
            stats['error'] = str(e)
        return stats

    def search_with_synthesis(self, source_key: str, query: str, top_k: int = 5) -> str:
        """
        Search and synthesize answer with Gemini.
        
        Args:
            source_key: Source to search
            query: User's question
            top_k: Number of chunks to retrieve
            
        Returns:
            Synthesized answer string
        """
        chunks = self._search_collection(source_key, query, top_k)
        return self._synthesize_with_gemini(query, chunks)


class ResearcherAgent:
    """
    Unified Researcher Agent with switchable backends.
    
    Maintains same interface as original, now with ChromaDB support.
    """
    
    def __init__(self, project_root: Optional[Path] = None, use_chromadb: bool = True):
        """
        Initialize researcher agent.
        
        Args:
            project_root: Path to project root
            use_chromadb: Use ChromaDB backend (True) or legacy File API (False)
        """
        self.use_chromadb = use_chromadb
        
        if use_chromadb:
            self.backend = ChromaDBBackend(project_root=project_root)
        else:
            # Import legacy backend
            from .researcher import ResearcherAgent as LegacyResearcher
            self.backend = LegacyResearcher(project_root=project_root)
    
    def search_theory(self, query: str) -> List[SearchResult]:
        """Search Think Like a Pancreas for diabetes management theory."""
        if self.use_chromadb:
            return self.backend.search_theory(query)
        else:
            return self.backend.search_theory(query)
    
    def search_camaps(self, query: str) -> List[SearchResult]:
        """Search CamAPS FX manual for hybrid closed-loop algorithm information."""
        if self.use_chromadb:
            return self.backend.search_camaps(query)
        else:
            return self.backend.search_camaps(query)
    
    def search_ypsomed(self, query: str) -> List[SearchResult]:
        """Search Ypsomed pump manual for hardware procedures."""
        if self.use_chromadb:
            return self.backend.search_ypsomed(query)
        else:
            return self.backend.search_ypsomed(query)
    
    def search_libre(self, query: str) -> List[SearchResult]:
        """Search FreeStyle Libre 3 manual for CGM information."""
        if self.use_chromadb:
            return self.backend.search_libre(query)
        else:
            return self.backend.search_libre(query)

    def search_ada_standards(self, query: str, sections: List[str] = None) -> List[SearchResult]:
        """
        Search ADA Standards of Care 2026 for evidence-based recommendations.

        Args:
            query: Search query
            sections: Optional list of section numbers to focus on

        Returns:
            List of SearchResult objects
        """
        if self.use_chromadb:
            return self.backend.search_ada_standards(query, sections)
        else:
            # Legacy fallback - no section filtering
            return []

    def search_australian_guidelines(self, query: str) -> List[SearchResult]:
        """
        Search Australian Diabetes Guidelines for technology recommendations.

        Particularly valuable for Sections 3.1-3.3 on diabetes technology.

        Args:
            query: Search query

        Returns:
            List of SearchResult objects
        """
        if self.use_chromadb:
            return self.backend.search_australian_guidelines(query)
        else:
            return []

    def search_clinical_guidelines(self, query: str) -> List[SearchResult]:
        """
        Search both clinical guideline sources combined.

        Args:
            query: Search query

        Returns:
            Combined list of SearchResult objects
        """
        if self.use_chromadb:
            return self.backend.search_clinical_guidelines(query)
        else:
            return []

    def search_research_papers(self, query: str) -> List[SearchResult]:
        """
        Search PubMed research papers in the knowledge base.

        Args:
            query: Search query

        Returns:
            List of SearchResult objects from research papers
        """
        if self.use_chromadb:
            return self.backend.search_research_papers(query)
        else:
            return []

    def search_openaps_docs(self, query: str) -> List[SearchResult]:
        """
        Search OpenAPS community documentation.

        Args:
            query: Search query

        Returns:
            List of SearchResult objects from OpenAPS docs
        """
        if self.use_chromadb:
            return self.backend.search_openaps_docs(query)
        else:
            return []

    def search_all_collections(
        self,
        query: str,
        top_k: int = 5,
        deduplicate: bool = True
    ) -> List[SearchResult]:
        """
        Search ALL collections and return merged, deduplicated results.

        This is the recommended method for comprehensive queries that should
        search across all knowledge sources (ada_guidelines, openaps_docs,
        pubmed_research, glooko_data, etc.).

        Args:
            query: Search query
            top_k: Number of results to return
            deduplicate: Whether to remove near-duplicate results

        Returns:
            List of SearchResult objects sorted by confidence
        """
        if self.use_chromadb:
            return self.backend.search_all_collections(
                query, top_k=top_k, deduplicate=deduplicate
            )
        else:
            # Fallback: search multiple sources manually
            all_results = []
            all_results.extend(self.search_theory(query))
            all_results.extend(self.search_clinical_guidelines(query))
            all_results.sort(key=lambda x: x.confidence, reverse=True)
            return all_results[:top_k]

    def search_with_citations(self, query: str, top_k: int = 5) -> List[dict]:
        """
        Search all collections and return results with formatted citations.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of dicts with 'content', 'citation', and 'metadata'
        """
        if self.use_chromadb:
            return self.backend.search_with_citations(query, top_k)
        else:
            results = self.search_all_collections(query, top_k)
            return [
                {
                    'content': r.quote,
                    'citation': f"[Source: {r.source} | Confidence: {r.confidence:.2f}]",
                    'metadata': {
                        'source': r.source,
                        'confidence': r.confidence,
                        'page': r.page_number,
                        'context': r.context
                    }
                }
                for r in results
            ]

    def search_multiple(self, query: str, sources: list[str]) -> dict[str, List[SearchResult]]:
        """
        Search multiple sources in parallel.
        
        Args:
            query: Search query
            sources: List of source keys
            
        Returns:
            Dictionary mapping source keys to results
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = {}
        search_map = {
            "theory": self.search_theory,
            "camaps": self.search_camaps,
            "ypsomed": self.search_ypsomed,
            "libre": self.search_libre,
            "clinical_guidelines": self.search_clinical_guidelines,
            "ada_standards": self.search_ada_standards,
            "australian_guidelines": self.search_australian_guidelines,
            "research_papers": self.search_research_papers,
            "openaps_docs": self.search_openaps_docs,
            "pubmed_research": self.search_research_papers,  # Alias
            "glooko_data": lambda q: [],  # Placeholder - handled by GlookoQueryAgent
        }
        
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


if __name__ == "__main__":
    """Test ChromaDB backend performance."""
    from dotenv import load_dotenv
    import sys
    
    # Load environment
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
    
    print("=" * 60)
    print("ChromaDB Researcher Backend Test")
    print("=" * 60)
    
    try:
        print("\nInitializing ChromaDB backend...")
        researcher = ResearcherAgent(use_chromadb=True)
        
        test_query = "What is Ease-off mode?"
        print(f"\nTest Query: {test_query}")
        print("-" * 60)
        
        # Test search
        start = time.time()
        results = researcher.search_camaps(test_query)
        elapsed = time.time() - start
        
        print(f"\nSearch completed in {elapsed:.2f}s")
        print(f"Found {len(results)} relevant chunks:\n")
        
        for i, result in enumerate(results[:3], 1):
            page = f"Page {result.page_number}" if result.page_number else "No page"
            print(f"{i}. [{result.source}, {page}] (Confidence: {result.confidence:.2%})")
            print(f"   {result.quote[:200]}...")
            print()
        
        print("=" * 60)
        print("Test completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
