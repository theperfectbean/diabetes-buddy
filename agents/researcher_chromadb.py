"""
ChromaDB-based RAG Researcher Agent for Diabetes Buddy

Fast local vector search replacing remote file-based API calls.
One-time PDF processing (~3min), then <5s queries forever.
"""

from dotenv import load_dotenv
load_dotenv()

# Force IPv4 before any Google API imports
from . import network  # noqa: F401

import os
import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
import hashlib
import sys

import chromadb
from chromadb.config import Settings
from .llm_provider import LLMFactory, GenerationConfig
import PyPDF2

import logging
logger = logging.getLogger(__name__)

USER_DEVICE_CONFIDENCE_BOOST = 0.35


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
    fast semantic search without repeated remote API calls.

    PDFs are auto-discovered by scanning configured directories.
    """

    # Directories to scan for PDFs (relative to project root)
    # Format: {directory: trust_level}
    PDF_DIRECTORIES = {
        "docs/manuals/algorithm": 0.85,    # Algorithm documentation (high trust)
        "docs/manuals/hardware": 0.85,     # Hardware manuals (high trust)
        "docs/theory": 0.8,                # Theory/guidelines
        "docs/knowledge-sources": 0.8,     # Structured knowledge sources
        "docs/user-sources": 0.9,          # User-uploaded sources (high trust)
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
        
        # Use the same provider for embeddings (local embeddings in Groq provider)
        self.embedding_llm = self.llm

        # Expose configured embedding model for diagnostics and downstream code
        try:
            self.embedding_model = getattr(self.embedding_llm, "embedding_model", None) or (self.embedding_llm.get_model_info().model_name if hasattr(self.embedding_llm, 'get_model_info') else None)
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

        # Discover PDFs and build path/name mappings
        self.pdf_paths = {}      # source_key -> relative path
        self.source_names = {}   # source_key -> human-readable name
        self.source_trust = {}   # source_key -> trust level
        self._discover_pdfs()

        # Initialize collections (creates if needed)
        self._init_collections()

    def _pdf_to_source_key(self, pdf_path: Path) -> str:
        """Generate a collection-safe source key from PDF path."""
        # Use stem (filename without extension), lowercase, replace spaces/special chars
        name = pdf_path.stem.lower()
        # Replace problematic characters with underscores
        for char in [' ', '-', '.', '(', ')', '[', ']', ',']:
            name = name.replace(char, '_')
        # Remove consecutive underscores and trim
        while '__' in name:
            name = name.replace('__', '_')
        return name.strip('_')[:63]  # ChromaDB collection name limit

    def _pdf_to_display_name(self, pdf_path: Path) -> str:
        """Generate a human-readable name from PDF filename."""
        name = pdf_path.stem
        # Replace underscores and hyphens with spaces
        name = name.replace('_', ' ').replace('-', ' ')
        # Title case
        return name.title()

    def _discover_pdfs(self):
        """Scan configured directories for PDFs."""
        for dir_path, trust_level in self.PDF_DIRECTORIES.items():
            full_dir = self.project_root / dir_path
            if not full_dir.exists():
                continue

            # Recursively find all PDFs in this directory
            for pdf_path in full_dir.rglob("*.pdf"):
                source_key = self._pdf_to_source_key(pdf_path)

                # Handle duplicate keys by appending parent dir
                if source_key in self.pdf_paths:
                    parent = pdf_path.parent.name
                    source_key = f"{parent}_{source_key}"[:63]

                rel_path = pdf_path.relative_to(self.project_root)
                self.pdf_paths[source_key] = str(rel_path)
                self.source_names[source_key] = self._pdf_to_display_name(pdf_path)
                self.source_trust[source_key] = trust_level

    def _init_collections(self):
        """Initialize or load ChromaDB collections for discovered PDFs."""
        for source_key, rel_path in self.pdf_paths.items():
            collection = self.chroma_client.get_or_create_collection(
                name=source_key,
                metadata={"hnsw:space": "cosine"}
            )

            # Check if collection is empty (needs processing)
            if collection.count() == 0:
                pdf_path = self.project_root / rel_path
                if pdf_path.exists():
                    print(f"🔧 Processing {self.source_names[source_key]} for first time...")
                    self._process_pdf(source_key, pdf_path, collection)
                    print(f"✅ {self.source_names[source_key]} ready!")
    
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
        Embed a batch of texts using local embeddings.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        try:
            return self.embedding_llm.embed_text(texts)
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
            
            # Log for each chunk in batch
            for j, chunk in enumerate(batch):
                chunk_num = i + j + 1
                source_name = self.source_names.get(source_key, source_key)
                logger.info(f"Indexed chunk {chunk_num}/{len(all_chunks)} for {source_name}")
            
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
                "source_name": self.source_names.get(source_key, source_key),
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

        # Generate query embedding using same model as indexing (ensures dimension consistency)
        try:
            query_embedding = self.embedding_llm.embed_text([query])[0]
        except Exception as e:
            print(f"Error embedding query: {e}")
            return []

        # Search ChromaDB using pre-computed embedding (not query_texts)
        # This ensures dimension consistency between indexing and querying
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count())
            )
        except Exception as e:
            # Gracefully skip collections with embedding dimension mismatches
            if "dimension" in str(e).lower():
                logger.debug(f"Skipping collection {source_key}: embedding dimension mismatch")
                return []
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
                
                # Add keyword matching bonus for better relevance
                query_terms = query.lower().split()
                doc_lower = doc.lower()
                keyword_matches = sum(1 for term in query_terms if len(term) > 2 and term in doc_lower)
                if keyword_matches > 0:
                    # Boost by +0.1 per keyword match (max 3 keywords)
                    keyword_boost = min(0.3, keyword_matches * 0.1)
                    confidence = min(1.0, confidence + keyword_boost)
                    logger.debug(f"Keyword boost: {keyword_matches} matches, +{keyword_boost:.2f}")

                # Detect device collections - match common device patterns
                device_patterns = [
                    'camaps', 'cam_aps', 'fx', 'omnipod', 'tandem', 'control_iq', 'tslim',
                    'medtronic', '780g', '770g', 'guardian', 'ilet', 'bionic',
                    'dexcom', 'g6', 'g7', 'libre', 'freestyle',
                    'ypsomed', 'ypso', 'mylife', 'loop', 'androidaps', 'openaps',
                    'user-', 'user_'  # Also include user-prefixed collections
                ]
                source_key_lower = source_key.lower()
                is_user_device = any(pattern in source_key_lower for pattern in device_patterns)
                
                if is_user_device:
                    original_confidence = confidence
                    confidence = min(1.0, confidence + USER_DEVICE_CONFIDENCE_BOOST)
                    logger.debug(f"Device boost: {source_key} confidence {original_confidence:.3f} -> {confidence:.3f}")

                source_name = self.source_names.get(source_key, source_key)
                context = f"Retrieved from {source_name}"
                if is_user_device:
                    context = f"Retrieved from user device source: {source_name}"

                search_results.append(SearchResult(
                    quote=doc,
                    page_number=metadata.get('page'),
                    confidence=confidence,
                    source=source_name,
                    context=context
                ))
        
        return search_results
    
    def _synthesize_with_llm(self, query: str, chunks: List[SearchResult]) -> str:
        """
        DEPRECATED: Use synthesize_answer() instead.
        Synthesize an answer using the configured LLM with retrieved chunks.
        
        Args:
            query: User's question
            chunks: Retrieved context chunks
            
        Returns:
            Synthesized answer
        """
        return self.synthesize_answer(query, chunks, provider=None, model=None)

    def synthesize_answer(
        self,
        query: str,
        chunks: List[SearchResult],
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        """
        Provider-agnostic synthesis of answers using retrieved chunks.
        
        Args:
            query: User's question
            chunks: Retrieved context chunks
            provider: LLM provider (defaults to configured provider)
            model: Specific model to use (optional)
            
        Returns:
            Dict with keys: {answer, llm_provider, llm_model, tokens_used, estimated_cost, cache_enabled}
        """
        if not chunks:
            return {
                "answer": "No relevant information found in the knowledge base for this query.",
                "llm_provider": "none",
                "llm_model": "none",
                "tokens_used": {"input": 0, "output": 0},
                "estimated_cost": 0.0,
                "cache_enabled": False,
            }
        
        # Build context from chunks
        context_parts = []
        cache_tags = set()  # Track which chunks are cacheable
        
        for i, chunk in enumerate(chunks, 1):
            page_info = f", Page {chunk.page_number}" if chunk.page_number else ""
            context_parts.append(
                f"[Context {i}] ({chunk.source}{page_info}):\n{chunk.quote}\n"
            )
            
            # Tag chunks from ADA and guideline sources for caching
            if any(tag in chunk.source.lower() for tag in ["ada", "guideline", "australian", "standard"]):
                cache_tags.add(f"cacheable_{i}")
        
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
            # Get or create LLM provider
            if provider:
                from .llm_provider import LLMFactory
                LLMFactory.reset_provider()  # Reset to allow provider switch
                llm = LLMFactory.get_provider(provider_type=provider)
            else:
                llm = self.llm
            
            # Track provider and model
            provider_name = provider or (llm.provider_name if hasattr(llm, 'provider_name') else 'unknown')
            model_name = model or (llm.model_name if hasattr(llm, 'model_name') else 'unknown')
            
            # Check if caching should be enabled (for guideline queries)
            cache_enabled = len(cache_tags) > 0 and provider_name == "groq"
            if cache_enabled:
                os.environ["GROQ_ENABLE_CACHING"] = "true"
            
            # Generate answer
            answer = llm.generate_text(
                prompt=prompt,
                config=GenerationConfig(temperature=0.7),
            )
            
            # Calculate token usage and cost
            input_tokens = len(prompt.split()) * 1.3  # Rough estimate
            output_tokens = len(answer.split()) * 1.3
            estimated_cost = 0.0
            
            # If it's Groq, calculate actual cost
            if provider_name == "groq" and hasattr(llm, 'calculate_cost'):
                estimated_cost = llm.calculate_cost(int(input_tokens), int(output_tokens), model_name)
                # Reduce cost by 50% if caching enabled and used
                if cache_enabled:
                    estimated_cost *= 0.75  # 25% reduction (conservative)
            
            return {
                "answer": answer,
                "llm_provider": provider_name,
                "llm_model": model_name,
                "tokens_used": {"input": int(input_tokens), "output": int(output_tokens)},
                "estimated_cost": round(estimated_cost, 6),
                "cache_enabled": cache_enabled,
            }
            
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            # Fallback to formatted chunks
            fallback_answer = "\n\n".join([
                f"{chunk.quote} ({chunk.source}, Page {chunk.page_number})"
                for chunk in chunks
            ])
            return {
                "answer": fallback_answer,
                "llm_provider": "fallback",
                "llm_model": "formatted_chunks",
                "tokens_used": {"input": 0, "output": 0},
                "estimated_cost": 0.0,
                "cache_enabled": False,
            }

    
    def search_pdf_collection(self, source_key: str, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Search any discovered PDF collection by its source key.

        Args:
            source_key: The collection key (use list_pdf_collections() to see available keys)
            query: Search query
            top_k: Number of results to return

        Returns:
            List of SearchResult objects
        """
        if source_key not in self.pdf_paths:
            return []
        return self._search_collection(source_key, query, top_k)

    def search_all_pdfs(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Search all discovered PDF collections and merge results.

        Args:
            query: Search query
            top_k: Number of results per collection

        Returns:
            List of SearchResult objects sorted by confidence
        """
        all_results = []
        for source_key in self.pdf_paths.keys():
            try:
                results = self._search_collection(source_key, query, top_k)
                # Apply source trust weighting
                trust = self.source_trust.get(source_key, 0.7)
                for r in results:
                    r.confidence = r.confidence * trust
                all_results.extend(results)
            except Exception:
                pass
        all_results.sort(key=lambda x: x.confidence, reverse=True)
        return all_results[:top_k * 2]  # Return more results from combined search

    def list_pdf_collections(self) -> dict:
        """
        List all discovered PDF collections.

        Returns:
            Dict mapping source_key to {path, name, trust}
        """
        return {
            key: {
                "path": self.pdf_paths[key],
                "name": self.source_names[key],
                "trust": self.source_trust[key]
            }
            for key in self.pdf_paths
        }

    def search_ada_standards(self, query: str, sections: List[str] = None, top_k: int = 5) -> List[SearchResult]:
        """
        Search ADA Standards of Care (highest trust source).

        The ADA Standards of Care represent authoritative clinical practice guidelines
        and are assigned the highest trust level (1.0) in search rankings.

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
            List of SearchResult objects with confidence=1.0 (highest trust)
        """
        try:
            collection = self.chroma_client.get_collection(name="ada_standards")
        except Exception:
            # Collection doesn't exist yet (not ingested)
            return []

        if collection.count() == 0:
            return []

        # Enhance query with section context if specified
        if sections:
            section_context = f" (focusing on Sections {', '.join(sections)})"
            enhanced_query = query + section_context
        else:
            enhanced_query = query

        # Search ChromaDB
        try:
            results = collection.query(
                query_texts=[enhanced_query],
                n_results=min(top_k, collection.count())
            )
        except Exception as e:
            print(f"Error querying ada_standards collection: {e}")
            return []

        # Convert to SearchResult objects with highest trust (1.0)
        search_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i] if results['distances'] else 0.5

                # ADA Standards get highest trust (1.0) - authoritative clinical guidelines
                source_trust = 1.0
                query_relevance = 1.0 - (distance / 2.0)
                confidence = query_relevance * source_trust

                # Build rich source info from metadata
                section = metadata.get('section', '?')
                section_topic = metadata.get('section_topic', 'General')
                year = metadata.get('year', 2025)

                search_results.append(SearchResult(
                    quote=doc,
                    page_number=None,
                    confidence=confidence,
                    source=f"ADA Standards of Care {year}",
                    context=f"Section {section}: {section_topic}"
                ))

        return search_results

    def search(self, query: str, top_k: int = 5) -> dict:
        """
        General search across all configured sources.

        Returns a mapping of source_key -> list[SearchResult].
        """
        results = {}
        for source_key in self.pdf_paths.keys():
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
            collection = self.chroma_client.get_collection(name="research_papers")
        except Exception:
            # Collection doesn't exist yet (no papers ingested)
            return []

        if collection.count() == 0:
            return []

        # Search ChromaDB
        try:
            results = collection.query(
                query_texts=[query],
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

                # Use distance-based confidence scaled by source trustworthiness (0.7)
                source_trust = 0.7
                query_relevance = 1.0 - (distance / 2.0)
                confidence = query_relevance * source_trust

                search_results.append(SearchResult(
                    quote=doc,
                    page_number=None,
                    confidence=confidence,
                    source="PubMed Research Paper",
                    context=f"Retrieved from {metadata.get('document_id', 'unknown')}"
                ))

        return search_results

    def search_wikipedia_education(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Search Wikipedia T1D education content.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of SearchResult objects from Wikipedia articles
        """
        try:
            collection = self.chroma_client.get_collection(name="wikipedia_education")
        except Exception:
            # Collection doesn't exist yet
            return []

        if collection.count() == 0:
            return []

        # Search ChromaDB
        try:
            results = collection.query(
                query_texts=[query],
                n_results=min(top_k, collection.count())
            )
        except Exception as e:
            print(f"Error querying wikipedia_education collection: {e}")
            return []

        # Convert to SearchResult objects
        search_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i] if results['distances'] else 0.5

                # Use distance-based confidence scaled by source trustworthiness (0.8)
                source_trust = 0.8
                query_relevance = 1.0 - (distance / 2.0)
                confidence = query_relevance * source_trust

                search_results.append(SearchResult(
                    quote=doc,
                    page_number=None,
                    confidence=confidence,
                    source=f"Wikipedia ({metadata.get('title', 'unknown')})",
                    context=metadata.get('url', '')
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
            'ada_standards': self.search_ada_standards,
            'australian_guidelines': self.search_australian_guidelines,
            'research_papers': self.search_research_papers,
            'wikipedia_education': self.search_wikipedia_education,
        }

        # Add user-uploaded sources dynamically
        for key in self.pdf_paths:
            if key.startswith('user_'):
                search_methods[key] = lambda q, k=key: self._search_collection(k, q, 5)

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
            embeddings = self.embedding_llm.embed_text(texts)
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

    def refresh_user_sources(self):
        """Re-scan user sources directory and index new PDFs."""
        from .source_manager import UserSourceManager

        manager = UserSourceManager(self.project_root)
        pending = manager.get_pending_sources()

        for source in pending:
            file_path = Path(source.file_path)
            if file_path.exists():
                collection = self.chroma_client.get_or_create_collection(
                    name=source.collection_key,
                    metadata={"hnsw:space": "cosine"}
                )

                if collection.count() == 0:
                    print(f"🔧 Indexing {source.display_name}...")
                    self._process_pdf(
                        source.collection_key,
                        file_path,
                        collection
                    )
                    print(f"✅ {source.display_name} indexed!")

                manager.mark_indexed(source.collection_key, collection.count())

                # Add to internal mappings
                self.pdf_paths[source.collection_key] = source.file_path
                self.source_names[source.collection_key] = source.display_name
                self.source_trust[source.collection_key] = 0.9

    def delete_user_source_collection(self, collection_key: str):
        """Delete a ChromaDB collection for a user source."""
        try:
            self.chroma_client.delete_collection(name=collection_key)
            # Remove from internal mappings
            if collection_key in self.pdf_paths:
                del self.pdf_paths[collection_key]
            if collection_key in self.source_names:
                del self.source_names[collection_key]
            if collection_key in self.source_trust:
                del self.source_trust[collection_key]
        except Exception as e:
            print(f"Warning: Could not delete collection {collection_key}: {e}")

    def search_with_synthesis(self, source_key: str, query: str, top_k: int = 5) -> str:
        """
        Search and synthesize answer with the configured LLM.
        
        Args:
            source_key: Source to search
            query: User's question
            top_k: Number of chunks to retrieve
            
        Returns:
            Synthesized answer string
        """
        chunks = self._search_collection(source_key, query, top_k)
        return self._synthesize_with_llm(query, chunks)


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
        self.personalization_manager = None
        
        if use_chromadb:
            self.backend = ChromaDBBackend(project_root=project_root)
        else:
            # Import legacy backend
            from .researcher import ResearcherAgent as LegacyResearcher
            self.backend = LegacyResearcher(project_root=project_root)

    def set_personalization_manager(self, personalization_manager) -> None:
        """Attach a personalization manager for device-based boosts."""
        self.personalization_manager = personalization_manager

    def search_ada_standards(self, query: str, sections: List[str] = None, top_k: int = 5) -> List[SearchResult]:
        """
        Search ADA Standards of Care for evidence-based recommendations.

        This is the highest-trust source (confidence=1.0) for clinical guidelines.

        Args:
            query: Search query
            sections: Optional list of section numbers to focus on
            top_k: Number of results to return

        Returns:
            List of SearchResult objects with highest trust ranking
        """
        if self.use_chromadb:
            return self.backend.search_ada_standards(query, sections, top_k)
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



    def search_wikipedia_education(self, query: str) -> List[SearchResult]:
        """
        Search Wikipedia T1D education content.

        Args:
            query: Search query

        Returns:
            List of SearchResult objects from Wikipedia articles
        """
        if self.use_chromadb:
            return self.backend.search_wikipedia_education(query)
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
        search across all knowledge sources (ada_guidelines, pubmed_research,
        wikipedia_education, device_manuals, etc.).

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
            "clinical_guidelines": self.search_clinical_guidelines,
            "ada_standards": self.search_ada_standards,
            "australian_guidelines": self.search_australian_guidelines,
            "research_papers": self.search_research_papers,
            
            "wikipedia_education": self.search_wikipedia_education,
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


    def query_knowledge(self, query: str, top_k: int = 5, session_id: Optional[str] = None) -> List[SearchResult]:
        """
        Query ALL documentation collections for diabetes management knowledge.

        Dynamically discovers and searches all ChromaDB collections (excluding system collections).
        User device collections receive automatic confidence boost for personalized responses.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of SearchResult objects sorted by confidence
        """
        if not self.use_chromadb:
            return []

        all_results = []

        # Dynamically discover all collections in ChromaDB
        try:
            all_collections = self.backend.chroma_client.list_collections()
            searchable_collections = [
                col.name for col in all_collections
                if not col.name.startswith('_')  # Exclude system collections
                and col.count() > 0  # Only search non-empty collections
            ]
            
            logger.info(f"Searching {len(searchable_collections)} collections: {', '.join(searchable_collections[:10])}{'...' if len(searchable_collections) > 10 else ''}")
            
        except Exception as e:
            logger.error(f"Could not list ChromaDB collections: {e}")
            searchable_collections = []

        # Search each collection
        collection_results = {}
        for collection_name in searchable_collections:
            try:
                results = self.backend._search_collection(collection_name, query, top_k)
                collection_results[collection_name] = results
                all_results.extend(results)
                if results:
                    logger.debug(f"  {collection_name}: {len(results)} results (max conf: {max(r.confidence for r in results):.3f})")
            except Exception as e:
                logger.warning(f"Error searching {collection_name}: {e}")


        if self.personalization_manager and session_id:
            try:
                all_results = self.personalization_manager.apply_device_boost(
                    all_results,
                    session_id=session_id,
                )
            except Exception as exc:
                logger.warning(f"Personalization boost failed: {exc}")

        # Sort by confidence (already includes source trustworthiness) and return top results
        all_results.sort(key=lambda x: x.confidence, reverse=True)
        final_results = all_results[:top_k]
        
        return final_results


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
