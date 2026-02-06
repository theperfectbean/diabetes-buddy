"""Fast reingestion with model caching"""
import os
os.environ['TRANSFORMERS_OFFLINE'] = '0'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'

from sentence_transformers import SentenceTransformer
import chromadb
from pathlib import Path
import PyPDF2
from typing import List, Tuple
import time

print("Loading embedding model (one-time)...")
MODEL = SentenceTransformer(
    'sentence-transformers/all-mpnet-base-v2',
    cache_folder=os.path.expanduser('~/.cache/huggingface')
)
print("Model loaded ✓\n")

def embed_batch(texts: List[str]) -> List[List[float]]:
    return MODEL.encode(texts, show_progress_bar=False, batch_size=64).tolist()

def extract_text(pdf_path: Path) -> List[Tuple[str, int]]:
    pages = []
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text.strip():
                pages.append((text, i+1))
    return pages

def chunk_text(pages: List[Tuple[str, int]], chunk_size=800) -> List[Tuple[str, int]]:
    chunks = []
    for text, page_num in pages:
        words = text.split()
        for i in range(0, len(words), chunk_size):
            chunk = ' '.join(words[i:i+chunk_size])
            if chunk.strip():
                chunks.append((chunk, page_num))
    return chunks

def reingest_collection(name: str, pdf_path: str):
    print(f"Processing: {name}")
    print(f"PDF: {pdf_path}\n")
    
    print("1/4 Extracting text...")
    pages = extract_text(Path(pdf_path))
    print(f"    {len(pages)} pages ✓")
    
    print("2/4 Chunking...")
    chunks = chunk_text(pages)
    print(f"    {len(chunks)} chunks ✓")
    
    print("3/4 Embedding (batch_size=64)...")
    all_embeddings = []
    batch_size = 64
    for i in range(0, len(chunks), batch_size):
        batch_texts = [c[0] for c in chunks[i:i+batch_size]]
        embeddings = embed_batch(batch_texts)
        all_embeddings.extend(embeddings)
        print(f"    {min(i+batch_size, len(chunks))}/{len(chunks)}", end='\r')
    print(f"    {len(chunks)}/{len(chunks)} ✓")
    
    print("4/4 Storing in ChromaDB...")
    client = chromadb.PersistentClient(path='.cache/chromadb')
    
    try:
        client.delete_collection(name)
    except:
        pass
    
    collection = client.create_collection(name)
    collection.add(
        ids=[f"{name}_{i}" for i in range(len(chunks))],
        embeddings=all_embeddings,
        documents=[c[0] for c in chunks],
        metadatas=[{'page': c[1], 'source': name} for c in chunks]
    )
    print(f"    Stored {len(chunks)} chunks ✓\n")

print("=" * 60)
print("FAST REINGESTION")
print("=" * 60 + "\n")

collections = [
    ('standards_of_care_2026', 'docs/user-sources/standards-of-care-2026.pdf'),
]

start_time = time.time()

for name, path in collections:
    if Path(path).exists():
        reingest_collection(name, path)
    else:
        print(f"⚠️  Skipping {name}: {path} not found\n")

elapsed = time.time() - start_time
print("=" * 60)
print(f"COMPLETE in {elapsed:.1f}s")
print("=" * 60)
