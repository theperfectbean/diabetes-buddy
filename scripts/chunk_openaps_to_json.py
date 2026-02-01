import tiktoken
import os
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
import time
import gc
import logging

ENCODING = tiktoken.encoding_for_model("gpt-3.5-turbo")

logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
SOURCE_DIR = PROJECT_ROOT / "data" / "sources" / "openaps-docs"
OUTPUT_FILE = PROJECT_ROOT / "data" / "openaps_chunks.json"
EXCLUDE_PATTERNS = ["README.md", "LICENSE*", ".github/*", "CONTRIBUTING.md", "mkdocs.yml"]

def chunk_text(text):
    """Chunk text into overlapping segments using tiktoken (1000 tokens, 100 overlap)."""
    logger.debug(f"chunk_text() called with text length: {len(text)}")
    logger.debug("About to call ENCODING.encode()")
    tokens = ENCODING.encode(text)
    logger.debug(f"ENCODING.encode() completed, got {len(tokens)} tokens")
    chunk_size = 1000
    overlap_size = 100
    chunks = []
    start = 0
    logger.debug("Entering while loop")
    while start < len(tokens):
        logger.debug(f"Loop iteration: start={start}, len(tokens)={len(tokens)}")
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        logger.debug(f"Extracted chunk_tokens: {len(chunk_tokens)} tokens")
        logger.debug("About to call ENCODING.decode()")
        chunk_text = ENCODING.decode(chunk_tokens)
        logger.debug(f"ENCODING.decode() completed, chunk_text length: {len(chunk_text)}")
        logger.debug("About to append to chunks list")
        chunks.append(chunk_text)
        logger.debug(f"Appended chunk, chunks list now has {len(chunks)} items")
        if end >= len(tokens):
            logger.debug("Breaking out of loop - reached end of tokens")
            break
        start = max(0, end - overlap_size)
        logger.debug(f"Updated start to {start}")
    logger.debug(f"chunk_text() completed, returning {len(chunks)} chunks")
    return chunks

def infer_doc_type(file_path):
    """Infer document type from file path keywords."""
    path_str = str(file_path).lower()
    if any(k in path_str for k in ["setup", "install", "build"]):
        return "setup"
    elif any(k in path_str for k in ["algorithm", "oref", "autosens", "smb"]):
        return "algorithm"
    elif any(k in path_str for k in ["troubleshoot", "faq", "error", "problem"]):
        return "troubleshooting"
    elif any(k in path_str for k in ["safety", "warning", "limit", "risk"]):
        return "safety"
    else:
        return "general"

def process_and_chunk(start_index, num_files):
    all_chunks = []
    files_processed = 0
    total_chunks = 0
    doc_types_count = {"setup": 0, "algorithm": 0, "troubleshooting": 0, "safety": 0, "general": 0}
    errors = []

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
            logger.info(f"Reading file: {file_path}")
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            logger.info(f"File read, length: {len(content)} chars")
            logger.info(f"Starting tiktoken chunking...")
            chunks = chunk_text(content)
            logger.info(f"Created {len(chunks)} chunks")
            doc_type = infer_doc_type(str(rel_path))
            doc_types_count[doc_type] += len(chunks)

            logger.info(f"Creating metadata for {len(chunks)} chunks")
            # Create chunk objects
            for chunk_idx, chunk in enumerate(chunks):
                metadata = {
                    "source": "openaps_docs",
                    "repo": "openaps-docs",
                    "file_path": str(rel_path),
                    "confidence": 0.8,
                    "doc_type": doc_type,
                    "ingested_date": datetime.now(timezone.utc).isoformat()
                }
                chunk_obj = {
                    "id": f"openaps_{file_idx}_{chunk_idx}",
                    "text": chunk,
                    "metadata": metadata
                }
                all_chunks.append(chunk_obj)
                total_chunks += 1
                logger.debug(f"Processed chunk {chunk_idx+1}/{len(chunks)}")

            files_processed += 1

            # Memory management: gc after every file
            gc.collect()

            # Sleep after every 5 files
            if files_processed % 5 == 0:
                time.sleep(1)

        except Exception as e:
            print(f"Error processing {rel_path}: {e}")
            errors.append(f"File {rel_path}: {e}")

    return files_processed, total_chunks, doc_types_count, errors, all_chunks

def main():
    parser = argparse.ArgumentParser(description="Chunk OpenAPS documentation to JSON")
    parser.add_argument("--start-index", type=int, default=0, help="Starting index for file batch (default: 0)")
    parser.add_argument("--num-files", type=int, default=10, help="Number of files to process in this batch (default: 10)")
    args = parser.parse_args()

    start_time = datetime.now(timezone.utc)
    print(f"Starting OpenAPS chunking: start-index={args.start_index}, num-files={args.num_files}")

    # Process and chunk
    processed_files, total_chunks, doc_types_count, errors, all_chunks = process_and_chunk(args.start_index, args.num_files)

    # Save to JSON
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Writing {len(all_chunks)} chunks to JSON...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)
    logger.info(f"JSON written successfully")

    # Print report
    end_time = datetime.now(timezone.utc)
    duration = end_time - start_time

    print("=== OpenAPS Chunking Report ===")
    print(f"Start: {start_time.isoformat()}")
    print(f"Batch: start-index={args.start_index}, num-files={args.num_files}")
    print(f"\nFiles Processed: {processed_files} successfully")
    print(f"\nChunking:")
    print(f"- Total chunks created: {total_chunks}")
    print(f"- Average chunks per file: {total_chunks/processed_files if processed_files > 0 else 0:.1f}")
    print(f"- Doc types: {doc_types_count}")
    print(f"\nOutput: {OUTPUT_FILE} ({len(all_chunks)} chunks)")
    print(f"\nErrors: {errors if errors else '[none]'}")
    print(f"\nEnd: {end_time.isoformat()}")
    print(f"Duration: {duration.seconds // 60} minutes {duration.seconds % 60} seconds")


if __name__ == "__main__":
    main()
