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
from google import genai
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
    }

    # Human-readable source names
    SOURCE_NAMES = {
        "theory": "Think Like a Pancreas",
        "camaps": "CamAPS FX User Manual",
        "ypsomed": "Ypsomed Pump Manual",
        "libre": "FreeStyle Libre 3 Manual",
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
        # Configure API key
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.5-flash"
        self.embedding_model = "models/gemini-embedding-001"
        
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
            result = self.client.models.embed_content(
                model=self.embedding_model,
                contents=texts
            )
            return [emb.values for emb in result.embeddings]
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
            query_result = self.client.models.embed_content(
                model=self.embedding_model,
                contents=[query]
            )
            query_embedding = query_result.embeddings[0].values
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
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt]
            )
            return response.text.strip()
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
