import os
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
import chromadb
from chromadb.config import Settings
import tiktoken
import time
import gc

PROJECT_ROOT = Path(__file__).parent.parent
CHROMADB_PATH = PROJECT_ROOT / ".cache" / "chromadb"
SOURCE_DIR = PROJECT_ROOT / "data" / "sources" / "loopdocs"
EXCLUDE_PATTERNS = ["README.md", "LICENSE*", ".github/*", "CONTRIBUTING.md", "mkdocs.yml"]

def chunk_text(text):
    """Chunk text into overlapping segments using tiktoken (1000 tokens, 100 overlap)."""
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunk_size = 1000
    overlap_size = 100
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = enc.decode(chunk_tokens)
        chunks.append(chunk_text)
        if end >= len(tokens):
            break
        start = max(0, end - overlap_size)
    return chunks

def infer_doc_type(file_path):
    """Infer document type from file path keywords."""
    path_str = str(file_path).lower()
    if any(k in path_str for k in ["setup", "install", "build"]):
        return "setup"
    elif any(k in path_str for k in ["algorithm", "oref", "autosens", "smb", "dosing"]):
        return "algorithm"
    elif any(k in path_str for k in ["troubleshoot", "faq", "error", "problem"]):
        return "troubleshooting"
    elif any(k in path_str for k in ["safety", "warning", "limit", "risk"]):
        return "safety"
    else:
        return "general"

def process_and_ingest(start_index, num_files):
    client = chromadb.PersistentClient(path=str(CHROMADB_PATH), settings=Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection(name="loop_docs", metadata={"hnsw:space": "cosine"})
    chunks_before = collection.count()
    
    files_processed = 0
    total_chunks = 0
    doc_types_count = {"setup": 0, "algorithm": 0, "troubleshooting": 0, "safety": 0, "general": 0}
    errors = []
    batch_size = 1  # Conservative batching for memory safety
    
    # Get all files
    all_files = []
    for ext in ['*.md', '*.rst']:
        for file_path in SOURCE_DIR.rglob(ext):
            rel_path = file_path.relative_to(SOURCE_DIR)
            skip = False
            for pattern in EXCLUDE_PATTERNS:
                if pattern in str(rel_path):
                    skip = True
                    break
            if not skip:
                all_files.append((file_path, rel_path))
    
    # Sort files for consistent ordering
    all_files.sort(key=lambda x: x[1])
    
    # Slice the files for this batch
    batch_files = all_files[start_index:start_index + num_files]
    total_files_in_batch = len(batch_files)
    
    for file_idx, (file_path, rel_path) in enumerate(batch_files, start=start_index):
        try:
            print(f"Processing file {files_processed + 1}/{total_files_in_batch}: {rel_path}")
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            chunks = chunk_text(content)
            doc_type = infer_doc_type(str(rel_path))
            doc_types_count[doc_type] += len(chunks)
            
            # Prepare chunks
            file_chunks = []
            for chunk_idx, chunk in enumerate(chunks):
                metadata = {
                    "source": "loop_docs",
                    "repo": "loopdocs",
                    "file_path": str(rel_path),
                    "confidence": 0.8,
                    "doc_type": doc_type,
                    "ingested_date": datetime.now(timezone.utc).isoformat()
                }
                file_chunks.append({
                    'id': f"loop_{file_idx}_{chunk_idx}",
                    'document': chunk,
                    'metadata': metadata
                })
            
            # Upsert in batches of 1
            for i in range(0, len(file_chunks), batch_size):
                batch = file_chunks[i:i+batch_size]
                ids = [c['id'] for c in batch]
                documents = [c['document'] for c in batch]
                metadatas = [c['metadata'] for c in batch]
                retries = 3
                for attempt in range(retries):
                    try:
                        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
                        total_chunks += len(batch)
                        break
                    except Exception as e:
                        if attempt < retries - 1:
                            time.sleep(2 ** attempt)
                        else:
                            print(f"Failed to upsert batch for {rel_path}: {e}")
                            errors.append(f"File {rel_path} batch {i//batch_size}: {e}")
            
            files_processed += 1
            
            # Memory management: gc after every file
            gc.collect()
            
            # Sleep after every 5 files
            if files_processed % 5 == 0:
                time.sleep(1)
            
        except Exception as e:
            print(f"Error processing {rel_path}: {e}")
            errors.append(f"File {rel_path}: {e}")
    
    return files_processed, total_chunks, doc_types_count, errors, chunks_before, collection.count()

def main():
    parser = argparse.ArgumentParser(description="Ingest Loop documentation into ChromaDB in batches")
    parser.add_argument("--start-index", type=int, default=0, help="Starting index for file batch (default: 0)")
    parser.add_argument("--num-files", type=int, default=10, help="Number of files to process in this batch (default: 10)")
    args = parser.parse_args()
    
    start_time = datetime.now(timezone.utc)
    print(f"Starting Loop batch ingestion: start-index={args.start_index}, num-files={args.num_files}")
    
    # Process and ingest
    processed_files, total_chunks, doc_types_count, errors, chunks_before, chunks_after = process_and_ingest(args.start_index, args.num_files)
    
    # Validation query
    client = chromadb.PersistentClient(path=str(CHROMADB_PATH), settings=Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection(name="loop_docs", metadata={"hnsw:space": "cosine"})
    query_start = time.time()
    results = collection.query(query_texts=["How does Loop calculate insulin doses?"], n_results=3)
    query_time = (time.time() - query_start) * 1000
    
    # Print report
    end_time = datetime.now(timezone.utc)
    duration = end_time - start_time

    print("=== Loop Batch Ingestion Report ===")
    print(f"Start: {start_time.isoformat()}")
    print(f"Batch: start-index={args.start_index}, num-files={args.num_files}")
    print(f"\nFiles Processed: {processed_files} successfully")
    print(f"\nChunking:")
    print(f"- Total chunks created: {total_chunks}")
    print(f"- Average chunks per file: {total_chunks/processed_files if processed_files > 0 else 0:.1f}")
    print(f"- Doc types: {doc_types_count}")
    print(f"\nChromaDB:")
    print(f"- Collection: loop_docs")
    print(f"- Chunks before: {chunks_before}")
    print(f"- Chunks after: {chunks_after}")
    print(f"- Chunks added: {chunks_after - chunks_before}")
    print(f"\nValidation Query: \"How does Loop calculate insulin doses?\"")
    print("Top 3 Results:")
    if results['documents'] and results['documents'][0]:
        for j, (doc, meta, dist) in enumerate(zip(results['documents'][0], results['metadatas'][0], results['distances'][0])):
            snippet = doc[:100] + "..." if len(doc) > 100 else doc
            confidence = 1 - dist  # assuming cosine distance
            print(f"  {j+1}. {snippet} | doc_type: {meta['doc_type']} | confidence: {confidence:.3f}")
    else:
        print("  No results found")
    print(f"Query time: {query_time:.0f} ms")
    print(f"\nErrors: {errors if errors else '[none]'}")
    print(f"\nEnd: {end_time.isoformat()}")
    print(f"Duration: {duration.seconds // 60} minutes {duration.seconds % 60} seconds")

if __name__ == "__main__":
    main()