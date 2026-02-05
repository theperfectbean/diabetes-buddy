import json
import tempfile
import shutil
from pathlib import Path
import sys

import chromadb
from chromadb.config import Settings
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_dirs():
    config_dir = tempfile.mkdtemp()
    docs_dir = tempfile.mkdtemp()

    registry = {
        "version": "1.0.0",
        "insulin_pumps": {
            "test_pump": {
                "name": "Test Pump",
                "manufacturer": "Test Corp",
                "manual_url": "https://example.com/manual.pdf",
                "fetch_method": "direct",
                "direct_pdf_url": "https://example.com/manual.pdf",
                "version_pattern": "v(\\d+\\.\\d+)",
                "file_prefix": "test_pump_manual",
                "update_frequency_days": 180,
                "license": "Free",
            }
        },
        "cgm_devices": {
            "test_cgm": {
                "name": "Test CGM",
                "manufacturer": "Test Corp",
                "manual_url": "https://example.com/cgm.pdf",
                "fetch_method": "direct",
                "direct_pdf_url": "https://example.com/cgm.pdf",
                "version_pattern": "v(\\d+\\.\\d+)",
                "file_prefix": "test_cgm_manual",
                "update_frequency_days": 180,
                "license": "Free",
            }
        },
        "clinical_guidelines": {
            "test_guideline": {
                "name": "Test Guideline",
                "organization": "Test Org",
                "url": "https://example.com/guideline.pdf",
                "fetch_method": "direct",
                "direct_pdf_url": "https://example.com/guideline.pdf",
                "version_pattern": "(\\d{4})",
                "file_prefix": "test_guideline",
                "update_frequency_days": 365,
                "license": "Educational use",
            }
        },
        "fetch_config": {
            "user_agent": "TestBot/1.0",
            "timeout_seconds": 30,
            "max_retries": 3,
            "retry_delay_seconds": 1,
            "rate_limit_delay_seconds": 0,
        },
    }

    with open(Path(config_dir) / "device_registry.json", "w") as f:
        json.dump(registry, f)

    yield config_dir, docs_dir

    shutil.rmtree(config_dir)
    shutil.rmtree(docs_dir)


@pytest.fixture(scope="session")
def populated_chromadb():
    """
    Create and populate a ChromaDB instance with test knowledge samples.

    Returns:
        tuple: (client, llm)
    """
    temp_db_dir = tempfile.mkdtemp(prefix="test_chromadb_")

    try:
        client = chromadb.PersistentClient(
            path=temp_db_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        from agents.llm_provider import LLMFactory

        llm = LLMFactory.get_provider()
        test_embedding = llm.embed_text(["test"])[0]
        embedding_dim = len(test_embedding)

        fixtures_dir = Path(__file__).parent / "fixtures" / "knowledge_samples"

        collections_config = {
            "ada_standards": {
                "file": "ada_standards_sample.txt",
                "trust_level": 1.0,
                "source_name": "ADA Standards 2026",
                "context_type": "clinical_guideline",
            },
            "openaps_docs": {
                "file": "openaps_sample.txt",
                "trust_level": 0.8,
                "source_name": "OpenAPS Documentation",
                "context_type": "practical_guide",
            },
            "research_papers": {
                "file": "research_sample.txt",
                "trust_level": 0.7,
                "source_name": "PubMed Research",
                "context_type": "research_literature",
            },
        }

        for collection_name, config in collections_config.items():
            collection = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )

            sample_file = fixtures_dir / config["file"]
            if not sample_file.exists():
                print(f"Warning: Sample file not found: {sample_file}")
                continue

            with open(sample_file, "r", encoding="utf-8") as f:
                content = f.read()

            chunks = []
            current_chunk = []
            page_num = 1

            for line in content.split("\n"):
                if line.startswith("===") and current_chunk:
                    chunk_text = "\n".join(current_chunk).strip()
                    if chunk_text:
                        chunks.append((chunk_text, page_num))
                        page_num += 1
                    current_chunk = []
                current_chunk.append(line)

            if current_chunk:
                chunk_text = "\n".join(current_chunk).strip()
                if chunk_text:
                    chunks.append((chunk_text, page_num))

            if not chunks:
                print(f"Warning: No chunks extracted from {sample_file}")
                continue

            chunk_texts = [chunk[0] for chunk in chunks]
            try:
                embeddings = llm.embed_text(chunk_texts)
            except Exception as e:
                print(f"Warning: Could not generate embeddings: {e}")
                embeddings = [[0.0] * embedding_dim for _ in chunk_texts]

            ids = [f"{collection_name}_{i}" for i in range(len(chunks))]
            documents = chunk_texts
            metadatas = [
                {
                    "source": collection_name,
                    "source_name": config["source_name"],
                    "page": chunk[1],
                    "chunk_id": i,
                    "trust_level": config["trust_level"],
                    "context_type": config["context_type"],
                }
                for i, chunk in enumerate(chunks)
            ]

            collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )

        yield client, llm

    finally:
        shutil.rmtree(temp_db_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def researcher_with_test_data(populated_chromadb):
    """
    Create a ResearcherAgent backed by the populated test ChromaDB.
    """
    from agents.researcher_chromadb import ResearcherAgent, SearchResult

    client, llm = populated_chromadb
    temp_project_dir = tempfile.mkdtemp(prefix="test_project_")

    try:
        researcher = ResearcherAgent(project_root=Path(temp_project_dir))

        if hasattr(researcher, "backend"):
            researcher.backend.llm = llm
            researcher.backend.chroma_client = client

            def patched_search_ada(query, sections=None, top_k=5):
                try:
                    collection = client.get_collection(name="ada_standards")
                except Exception:
                    return []

                if collection.count() == 0:
                    return []

                query_embedding = llm.embed_text([query])[0]
                try:
                    results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=min(top_k, collection.count()),
                    )
                except Exception as e:
                    print(f"Error querying ada_standards: {e}")
                    return []

                search_results = []
                if results.get("documents") and results["documents"][0]:
                    for i, doc in enumerate(results["documents"][0]):
                        metadata = results["metadatas"][0][i]
                        distance = results["distances"][0][i] if results.get("distances") else 0.5
                        confidence = 1.0 - (distance / 2.0)

                        search_results.append(
                            SearchResult(
                                quote=doc,
                                page_number=metadata.get("page"),
                                confidence=confidence,
                                source="ada_standards",
                                context="ADA Standards",
                            )
                        )

                return search_results

            def patched_search_collection(source_key, query, top_k=5):
                try:
                    collection = client.get_collection(name=source_key)
                except Exception as e:
                    print(f"Warning: Collection '{source_key}' not found: {e}")
                    return []

                if collection.count() == 0:
                    return []

                query_embedding = llm.embed_text([query])[0]
                try:
                    results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=min(top_k, collection.count()),
                    )
                except Exception as e:
                    print(f"Error querying {source_key}: {e}")
                    return []

                search_results = []
                if results.get("documents") and results["documents"][0]:
                    for i, doc in enumerate(results["documents"][0]):
                        metadata = results["metadatas"][0][i]
                        distance = results["distances"][0][i] if results.get("distances") else 0.5
                        confidence = 1.0 - (distance / 2.0)

                        search_results.append(
                            SearchResult(
                                quote=doc,
                                page_number=metadata.get("page"),
                                confidence=confidence,
                                source=source_key,
                                context=f"Retrieved from {source_key}",
                            )
                        )

                return search_results

            researcher.backend.search_ada_standards = patched_search_ada
            researcher.backend._search_collection = patched_search_collection
            researcher.backend.search_openaps_docs = (
                lambda query, top_k=5: patched_search_collection("openaps_docs", query, top_k)
            )
            researcher.backend.search_research_papers = (
                lambda query, top_k=5: patched_search_collection("research_papers", query, top_k)
            )

            researcher.backend.collections = {
                "ada_standards": client.get_collection("ada_standards"),
                "openaps_docs": client.get_collection("openaps_docs"),
                "research_papers": client.get_collection("research_papers"),
            }

        yield researcher

    finally:
        shutil.rmtree(temp_project_dir, ignore_errors=True)

'''
import json
import tempfile
import shutil
from pathlib import Path
import sys

import chromadb
from chromadb.config import Settings
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_dirs():
    config_dir = tempfile.mkdtemp()
    docs_dir = tempfile.mkdtemp()

    registry = {
        "version": "1.0.0",
        "insulin_pumps": {
            "test_pump": {
                "name": "Test Pump",
                "manufacturer": "Test Corp",
                "manual_url": "https://example.com/manual.pdf",
                "fetch_method": "direct",
                "direct_pdf_url": "https://example.com/manual.pdf",
                "version_pattern": "v(\\d+\\.\\d+)",
                "file_prefix": "test_pump_manual",
                "update_frequency_days": 180,
                "license": "Free",
            }
        },
        "cgm_devices": {
            "test_cgm": {
                "name": "Test CGM",
                "manufacturer": "Test Corp",
                "manual_url": "https://example.com/cgm.pdf",
                "fetch_method": "direct",
                "direct_pdf_url": "https://example.com/cgm.pdf",
                "version_pattern": "v(\\d+\\.\\d+)",
                "file_prefix": "test_cgm_manual",
                "update_frequency_days": 180,
                "license": "Free",
            }
        },
        "clinical_guidelines": {
            "test_guideline": {
                "name": "Test Guideline",
                "organization": "Test Org",
                "url": "https://example.com/guideline.pdf",
                "fetch_method": "direct",
                "direct_pdf_url": "https://example.com/guideline.pdf",
                "version_pattern": "(\\d{4})",
                "file_prefix": "test_guideline",
                "update_frequency_days": 365,
                "license": "Educational use",
            }
        },
        "fetch_config": {
            "user_agent": "TestBot/1.0",
            "timeout_seconds": 30,
            "max_retries": 3,
            "retry_delay_seconds": 1,
            "rate_limit_delay_seconds": 0,
        },
    }

    with open(Path(config_dir) / "device_registry.json", "w") as f:
        json.dump(registry, f)

    yield config_dir, docs_dir

    shutil.rmtree(config_dir)
    shutil.rmtree(docs_dir)


@pytest.fixture(scope="session")
def populated_chromadb():
    """
    Create and populate a ChromaDB instance with test knowledge samples.

    Returns:
        tuple: (client, llm)
    """
    temp_db_dir = tempfile.mkdtemp(prefix="test_chromadb_")

    try:
        client = chromadb.PersistentClient(
            path=temp_db_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        from agents.llm_provider import LLMFactory

        llm = LLMFactory.get_provider()
        test_embedding = llm.embed_text(["test"])[0]
        embedding_dim = len(test_embedding)

        fixtures_dir = Path(__file__).parent / "fixtures" / "knowledge_samples"

        collections_config = {
            "ada_standards": {
                "file": "ada_standards_sample.txt",
                "trust_level": 1.0,
                "source_name": "ADA Standards 2026",
                "context_type": "clinical_guideline",
            },
            "openaps_docs": {
                "file": "openaps_sample.txt",
                "trust_level": 0.8,
                "source_name": "OpenAPS Documentation",
                "context_type": "practical_guide",
            },
            "research_papers": {
                "file": "research_sample.txt",
                "trust_level": 0.7,
                "source_name": "PubMed Research",
                "context_type": "research_literature",
            },
        }

        for collection_name, config in collections_config.items():
            collection = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )

            sample_file = fixtures_dir / config["file"]
            if not sample_file.exists():
                print(f"Warning: Sample file not found: {sample_file}")
                continue

            with open(sample_file, "r", encoding="utf-8") as f:
                content = f.read()

            chunks = []
            current_chunk = []
            page_num = 1

            for line in content.split("\n"):
                if line.startswith("===") and current_chunk:
                    chunk_text = "\n".join(current_chunk).strip()
                    if chunk_text:
                        chunks.append((chunk_text, page_num))
                        page_num += 1
                    current_chunk = []
                current_chunk.append(line)

            if current_chunk:
                chunk_text = "\n".join(current_chunk).strip()
                if chunk_text:
                    chunks.append((chunk_text, page_num))

            if not chunks:
                print(f"Warning: No chunks extracted from {sample_file}")
                continue

            chunk_texts = [chunk[0] for chunk in chunks]
            try:
                embeddings = llm.embed_text(chunk_texts)
            except Exception as e:
                print(f"Warning: Could not generate embeddings: {e}")
                embeddings = [[0.0] * embedding_dim for _ in chunk_texts]

            ids = [f"{collection_name}_{i}" for i in range(len(chunks))]
            documents = chunk_texts
            metadatas = [
                {
                    "source": collection_name,
                    "source_name": config["source_name"],
                    "page": chunk[1],
                    "chunk_id": i,
                    "trust_level": config["trust_level"],
                    "context_type": config["context_type"],
                }
                for i, chunk in enumerate(chunks)
            ]

            collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )

        yield client, llm

    finally:
        shutil.rmtree(temp_db_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def researcher_with_test_data(populated_chromadb):
    """
    Create a ResearcherAgent backed by the populated test ChromaDB.
    """
    from agents.researcher_chromadb import ResearcherAgent, SearchResult

    client, llm = populated_chromadb
    temp_project_dir = tempfile.mkdtemp(prefix="test_project_")

    try:
        researcher = ResearcherAgent(project_root=Path(temp_project_dir))

        if hasattr(researcher, "backend"):
            researcher.backend.llm = llm
            researcher.backend.chroma_client = client

            def patched_search_ada(query, sections=None, top_k=5):
                try:
                    collection = client.get_collection(name="ada_standards")
                except Exception:
                    return []

                if collection.count() == 0:
                    return []

                query_embedding = llm.embed_text([query])[0]
                try:
                    results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=min(top_k, collection.count()),
                    )
                except Exception as e:
                    print(f"Error querying ada_standards: {e}")
                    return []

                search_results = []
                if results.get("documents") and results["documents"][0]:
                    for i, doc in enumerate(results["documents"][0]):
                        metadata = results["metadatas"][0][i]
                        distance = results["distances"][0][i] if results.get("distances") else 0.5
                        confidence = 1.0 - (distance / 2.0)

                        search_results.append(
                            SearchResult(
                                quote=doc,
                                page_number=metadata.get("page"),
                                confidence=confidence,
                                source="ada_standards",
                                context="ADA Standards",
                            )
                        )

                return search_results

            def patched_search_collection(source_key, query, top_k=5):
                try:
                    collection = client.get_collection(name=source_key)
                except Exception as e:
                    print(f"Warning: Collection '{source_key}' not found: {e}")
                    return []

                if collection.count() == 0:
                    return []

                query_embedding = llm.embed_text([query])[0]
                try:
                    results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=min(top_k, collection.count()),
                    )
                except Exception as e:
                    print(f"Error querying {source_key}: {e}")
                    return []

                search_results = []
                if results.get("documents") and results["documents"][0]:
                    for i, doc in enumerate(results["documents"][0]):
                        metadata = results["metadatas"][0][i]
                        distance = results["distances"][0][i] if results.get("distances") else 0.5
                        confidence = 1.0 - (distance / 2.0)

                        search_results.append(
                            SearchResult(
                                quote=doc,
                                page_number=metadata.get("page"),
                                confidence=confidence,
                                source=source_key,
                                context=f"Retrieved from {source_key}",
                            )
                        )

                return search_results

            researcher.backend.search_ada_standards = patched_search_ada
            researcher.backend._search_collection = patched_search_collection

            researcher.backend.collections = {
                "ada_standards": client.get_collection("ada_standards"),
                "openaps_docs": client.get_collection("openaps_docs"),
                "research_papers": client.get_collection("research_papers"),
            }

        yield researcher

    finally:
        shutil.rmtree(temp_project_dir, ignore_errors=True)import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import pytest
import chromadb
from chromadb.config import Settings
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture
def temp_dirs():
    config_dir = tempfile.mkdtemp()
    docs_dir = tempfile.mkdtemp()

    registry = {
        "version": "1.0.0",
        "insulin_pumps": {
            "test_pump": {
                "name": "Test Pump",
                "manufacturer": "Test Corp",
                "manual_url": "https://example.com/manual.pdf",
                "fetch_method": "direct",
                "direct_pdf_url": "https://example.com/manual.pdf",
                "version_pattern": "v(\\d+\\.\\d+)",
                "file_prefix": "test_pump_manual",
                "update_frequency_days": 180,
                "license": "Free"
            }
        },
        "cgm_devices": {
            "test_cgm": {
                "name": "Test CGM",
                "manufacturer": "Test Corp",
                "manual_url": "https://example.com/cgm.pdf",
                "fetch_method": "direct",
                "direct_pdf_url": "https://example.com/cgm.pdf",
                "version_pattern": "v(\\d+\\.\\d+)",
                "file_prefix": "test_cgm_manual",
                "update_frequency_days": 180,
                "license": "Free"
            }
        },
        "clinical_guidelines": {
            "test_guideline": {
                "name": "Test Guideline",
                "organization": "Test Org",
                "url": "https://example.com/guideline.pdf",
                "fetch_method": "direct",
                "direct_pdf_url": "https://example.com/guideline.pdf",
                "version_pattern": "(\\d{4})",
                "file_prefix": "test_guideline",
                "update_frequency_days": 365,
                "license": "Educational use"
            }
        },
        "fetch_config": {
            "user_agent": "TestBot/1.0",
            "timeout_seconds": 30,
            "max_retries": 3,
            "retry_delay_seconds": 1,
            "rate_limit_delay_seconds": 0
        }
    }

    with open(Path(config_dir) / "device_registry.json", 'w') as f:
        json.dump(registry, f)

    yield config_dir, docs_dir

    shutil.rmtree(config_dir)
    shutil.rmtree(docs_dir)


@pytest.fixture(scope="session")
def populated_chromadb():
    """
    Pytest fixture that creates and populates a ChromaDB instance with test knowledge samples.
    
    This fixture:
    1. Creates a temporary ChromaDB instance
    2. Ingests sample documents from tests/fixtures/knowledge_samples/
    3. Adds proper metadata (confidence scores, source labels)
    4. Yields the populated database to tests
    5. Cleans up after test suite completes
    
    Returns:
        tuple: (ChromaDB client, LLM provider) - both using consistent embedding dimension
    """
    # Create temporary directory for test ChromaDB
    temp_db_dir = tempfile.mkdtemp(prefix="test_chromadb_")
    
    try:
        # Initialize ChromaDB client
        client = chromadb.PersistentClient(
            path=temp_db_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Import LLM provider for embeddings
        from agents.llm_provider import LLMFactory
        llm = LLMFactory.get_provider()
        
        # Detect embedding dimension by generating a test embedding
        test_embedding = llm.embed_text(["test"])[0]
        embedding_dim = len(test_embedding)
        print(f"Using embedding dimension: {embedding_dim}")
        
        # Path to test fixtures
        fixtures_dir = Path(__file__).parent / "fixtures" / "knowledge_samples"
        
        # Define collections with their metadata
        collections_config = {
            "ada_standards": {
                "file": "ada_standards_sample.txt",
                "trust_level": 1.0,
                "source_name": "ADA Standards 2026",
                "context_type": "clinical_guideline"
            },
            "openaps_docs": {
                "file": "openaps_sample.txt",
                "trust_level": 0.8,
                "source_name": "OpenAPS Documentation",
                "context_type": "practical_guide"
            },
            "research_papers": {
                "file": "research_sample.txt",
                "trust_level": 0.7,
                "source_name": "PubMed Research",
                "context_type": "research_literature"
            }
        }
        
        # Create and populate each collection
        for collection_name, config in collections_config.items():
            # Create collection without default embedding function
            # This forces explicit embedding provision during query
            collection = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=None  # No automatic embeddings
            )
            
            # Read sample file
            sample_file = fixtures_dir / config["file"]
            if not sample_file.exists():
                print(f"Warning: Sample file not found: {sample_file}")
                continue
                
            with open(sample_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split content into chunks (by sections marked with ===)
            chunks = []
            current_chunk = []
            page_num = 1
            
            for line in content.split('\n'):
                if line.startswith('===') and current_chunk:
                    # End of a chunk
                    chunk_text = '\n'.join(current_chunk).strip()
                    if chunk_text:
                        chunks.append((chunk_text, page_num))
                        page_num += 1
                    current_chunk = []
                current_chunk.append(line)
            
            # Add final chunk
            if current_chunk:
                chunk_text = '\n'.join(current_chunk).strip()
                if chunk_text:
                    chunks.append((chunk_text, page_num))
            
            if not chunks:
                print(f"Warning: No chunks extracted from {sample_file}")
                continue
            
            # Generate embeddings
            chunk_texts = [chunk[0] for chunk in chunks]
            try:
                embeddings = llm.embed_text(chunk_texts)
            except Exception as e:
                print(f"Warning: Could not generate embeddings: {e}")
                # Create zero embeddings as fallback with correct dimension
                embeddings = [[0.0] * embedding_dim for _ in chunk_texts]
            
            # Prepare data for ChromaDB
            ids = [f"{collection_name}_{i}" for i in range(len(chunks))]
            documents = chunk_texts
            metadatas = [
                {
                    "source": collection_name,
                    "source_name": config["source_name"],
                    "page": chunk[1],
                    "chunk_id": i,
                    "trust_level": config["trust_level"],
                    "context_type": config["context_type"]
                }
                for i, chunk in enumerate(chunks)
            ]
            
            # Add to collection
            collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            
            print(f"✓ Populated {collection_name} with {len(chunks)} chunks (trust={config['trust_level']})")
        
        # Yield both client and LLM provider for consistency
        yield (client, llm)
        
    finally:
        # Cleanup temporary directory
        shutil.rmtree(temp_db_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def researcher_with_test_data(populated_chromadb):
    """
    Pytest fixture that creates a ResearcherAgent with populated ChromaDB.
    
    This creates a real ResearcherAgent instance backed by the populated
    test ChromaDB, allowing integration tests to verify actual RAG retrieval.
    
    Returns:
        ResearcherAgent with populated knowledge base collections
    """
    # Import after ensuring path is set
    from agents.researcher_chromadb import ResearcherAgent
    
    # Unpack fixture which now returns (client, llm)
    client, llm = populated_chromadb
    
    # Create temporary project directory
    temp_project_dir = tempfile.mkdtemp(prefix="test_project_")
    
    try:
        # Create a minimal ResearcherAgent with custom backend
        researcher = ResearcherAgent(project_root=Path(temp_project_dir))
        
        # Replace the backend's ChromaDB client and LLM with our test versions
        if hasattr(researcher, 'backend'):
            # Use the same LLM for embeddings (critical for dimension matching!)
            researcher.backend.llm = llm
            researcher.backend.chroma_client = client
            
                        # Monkey-patch search methods to use query_embeddings instead of query_texts
                        # This ensures we use the same 768-dim Gemini embeddings for both indexing and querying
                        original_search_ada = researcher.backend.search_ada_standards
            
                        def patched_search_ada(query, sections=None, top_k=5):
                            try:
                                collection = client.get_collection(name="ada_standards")
                            except Exception:
                                return []
                
                            if collection.count() == 0:
                                return []
                
                            # Generate query embedding using our LLM
                            query_embedding = llm.embed_text([query])[0]
                
                            # Query with embeddings instead of texts
                            try:
                                results = collection.query(
                                    query_embeddings=[query_embedding],
                                    n_results=min(top_k, collection.count())
                                )
                            except Exception as e:
                                print(f"Error querying ada_standards: {e}")
                                return []
                
                            # Convert to SearchResult
                            from agents.researcher_chromadb import SearchResult
                            search_results = []
                            if results['documents'] and results['documents'][0]:
                                for i, doc in enumerate(results['documents'][0]):
                                    metadata = results['metadatas'][0][i]
                                    distance = results['distances'][0][i] if results['distances'] else 0.5
                                    confidence = 1.0 - (distance / 2.0)
                        
                                    search_results.append(SearchResult(
                                        quote=doc,
                                        page_number=metadata.get('page'),
                                        confidence=confidence,
                                        source="ada_standards",
                                        context="ADA Standards"
                                    ))
                
                            return search_results
            
                        researcher.backend.search_ada_standards = patched_search_ada
            
                        # Patch the generic _search_collection as well
                        def patched_search_collection(source_key, query, top_k=5):
                            try:
                                collection = client.get_collection(name=source_key)
                            except Exception as e:
                                print(f"Warning: Collection '{source_key}' not found: {e}")
                                return []
                
                            if collection.count() == 0:
                                return []
                
                            # Generate query embedding
                            query_embedding = llm.embed_text([query])[0]
                
                            try:
                                results = collection.query(
                                    query_embeddings=[query_embedding],
                                    n_results=min(top_k, collection.count())
                                )
                            except Exception as e:
                                print(f"Error querying {source_key} collection: {e}")
                                return []
                
                            # Convert to SearchResult
                            from agents.researcher_chromadb import SearchResult
                            search_results = []
                            if results['documents'] and results['documents'][0]:
                                for i, doc in enumerate(results['documents'][0]):
                                    metadata = results['metadatas'][0][i]
                                    distance = results['distances'][0][i] if results['distances'] else 0.5
                                    confidence = 1.0 - (distance / 2.0)
                        
                                    search_results.append(SearchResult(
                                        quote=doc,
                                        page_number=metadata.get('page'),
                                        confidence=confidence,
                                        source=source_key,
                                        context=f"Retrieved from {source_key}"
                                    ))
                
                            return search_results
            
                        researcher.backend._search_collection = patched_search_collection
            
            # Update collection references to use test collections
            researcher.backend.collections = {
                "ada_standards": client.get_collection("ada_standards"),
                "openaps_docs": client.get_collection("openaps_docs"),
                "research_papers": client.get_collection("research_papers")
            }
        
        yield researcher
        
    finally:
        # Cleanup
        shutil.rmtree(temp_project_dir, ignore_errors=True)
'''
