#!/usr/bin/env python3
"""
Wikipedia Type 1 Diabetes Education Content Ingestion.

Fetches foundational T1D-related articles from Wikipedia and ingests them
into ChromaDB for the knowledge base.
"""

import time
import argparse
from pathlib import Path
from datetime import datetime, timezone
import chromadb
from chromadb.config import Settings
import tiktoken
import wikipedia

PROJECT_ROOT = Path(__file__).parent.parent
CHROMADB_PATH = PROJECT_ROOT / ".cache" / "chromadb"

# T1D-related Wikipedia articles to fetch
ARTICLES = [
    "Type 1 diabetes",
    "Dawn phenomenon",
    "Diabetic ketoacidosis",
    "Insulin therapy",
    "Continuous glucose monitoring",
    "Insulin pump",
]


def chunk_text(text, chunk_size=1000, overlap=100):
    """Chunk text into overlapping segments using tiktoken."""
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = enc.decode(chunk_tokens)
        chunks.append(chunk_text)
        if end >= len(tokens):
            break
        start = max(0, end - overlap)
    return chunks


def fetch_wikipedia_article(title):
    """Fetch a Wikipedia article by title."""
    try:
        page = wikipedia.page(title, auto_suggest=False)
        return {
            "title": page.title,
            "content": page.content,
            "url": page.url,
            "summary": page.summary,
        }
    except wikipedia.exceptions.DisambiguationError as e:
        # If disambiguation, try the first option
        print(f"Disambiguation for '{title}', trying first option: {e.options[0]}")
        try:
            page = wikipedia.page(e.options[0], auto_suggest=False)
            return {
                "title": page.title,
                "content": page.content,
                "url": page.url,
                "summary": page.summary,
            }
        except Exception as inner_e:
            print(f"Failed to fetch disambiguation option: {inner_e}")
            return None
    except wikipedia.exceptions.PageError:
        print(f"Page not found: '{title}'")
        return None
    except Exception as e:
        print(f"Error fetching '{title}': {e}")
        return None


def ingest_articles(articles_data):
    """Ingest Wikipedia articles into ChromaDB."""
    client = chromadb.PersistentClient(
        path=str(CHROMADB_PATH), settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_or_create_collection(
        name="wikipedia_education", metadata={"hnsw:space": "cosine"}
    )

    chunks_before = collection.count()
    total_chunks = 0
    errors = []

    for article in articles_data:
        try:
            # Chunk the content
            chunks = chunk_text(article["content"])

            # Prepare chunks for ingestion
            file_chunks = []
            # Create a safe ID prefix from title
            safe_title = article["title"].lower().replace(" ", "_").replace("/", "_")

            for chunk_idx, chunk in enumerate(chunks):
                metadata = {
                    "source": "wikipedia",
                    "title": article["title"],
                    "url": article["url"],
                    "confidence": 0.6,
                    "ingested_date": datetime.now(timezone.utc).isoformat(),
                }
                file_chunks.append(
                    {
                        "id": f"wiki_{safe_title}_{chunk_idx}",
                        "document": chunk,
                        "metadata": metadata,
                    }
                )

            # Upsert in batches of 10 (Wikipedia content is cleaner)
            batch_size = 10
            for i in range(0, len(file_chunks), batch_size):
                batch = file_chunks[i : i + batch_size]
                ids = [c["id"] for c in batch]
                documents = [c["document"] for c in batch]
                metadatas = [c["metadata"] for c in batch]

                retries = 3
                for attempt in range(retries):
                    try:
                        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
                        total_chunks += len(batch)
                        break
                    except Exception as e:
                        if attempt < retries - 1:
                            time.sleep(2**attempt)
                        else:
                            errors.append(f"Article '{article['title']}' batch {i // batch_size}: {e}")

            print(f"Processed '{article['title']}': {len(chunks)} chunks")

            # Rate limiting: 0.5 second between articles
            time.sleep(0.5)

        except Exception as e:
            print(f"Error processing '{article['title']}': {e}")
            errors.append(f"Article '{article['title']}': {e}")

    return total_chunks, errors, chunks_before, collection.count()


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Wikipedia T1D education content into ChromaDB"
    )
    parser.add_argument(
        "--articles",
        nargs="+",
        default=ARTICLES,
        help="List of Wikipedia article titles to fetch",
    )
    args = parser.parse_args()

    start_time = datetime.now(timezone.utc)
    print(f"Starting Wikipedia ingestion")
    print(f"Articles to fetch: {args.articles}")

    # Fetch Wikipedia articles
    print("\nFetching Wikipedia articles...")
    articles_data = []
    for title in args.articles:
        print(f"  Fetching: {title}")
        article = fetch_wikipedia_article(title)
        if article:
            articles_data.append(article)
            print(f"    ✓ Retrieved ({len(article['content'])} chars)")
        else:
            print(f"    ✗ Failed")
        time.sleep(0.5)  # Rate limiting

    print(f"\nSuccessfully retrieved {len(articles_data)}/{len(args.articles)} articles")

    if not articles_data:
        print("No articles fetched. Exiting.")
        return

    # Ingest into ChromaDB
    print("\nIngesting into ChromaDB...")
    total_chunks, errors, chunks_before, chunks_after = ingest_articles(articles_data)

    # Validation query
    client = chromadb.PersistentClient(
        path=str(CHROMADB_PATH), settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_or_create_collection(
        name="wikipedia_education", metadata={"hnsw:space": "cosine"}
    )
    query_start = time.time()
    results = collection.query(
        query_texts=["What causes dawn phenomenon?"], n_results=3
    )
    query_time = (time.time() - query_start) * 1000

    # Print report
    end_time = datetime.now(timezone.utc)
    duration = end_time - start_time

    print("\n" + "=" * 50)
    print("=== Wikipedia Education Content Ingestion Report ===")
    print("=" * 50)
    print(f"Start: {start_time.isoformat()}")
    print(f"\nArticles Requested: {len(args.articles)}")
    print(f"Articles Retrieved: {len(articles_data)}")
    print("\nArticles processed:")
    for article in articles_data:
        print(f"  - {article['title']}")
    print(f"\nChunking:")
    print(f"  - Chunk size: 1000 tokens")
    print(f"  - Overlap: 100 tokens")
    print(f"  - Total chunks created: {total_chunks}")
    print(
        f"  - Average chunks per article: {total_chunks / len(articles_data) if articles_data else 0:.1f}"
    )
    print(f"\nChromaDB:")
    print(f"  - Collection: wikipedia_education")
    print(f"  - Chunks before: {chunks_before}")
    print(f"  - Chunks after: {chunks_after}")
    print(f"  - Chunks added: {chunks_after - chunks_before}")
    print(f"\nValidation Query: \"What causes dawn phenomenon?\"")
    print("Top 3 Results:")
    if results["documents"] and results["documents"][0]:
        for j, (doc, meta, dist) in enumerate(
            zip(results["documents"][0], results["metadatas"][0], results["distances"][0])
        ):
            snippet = doc[:100] + "..." if len(doc) > 100 else doc
            confidence = 1 - dist  # cosine distance
            print(
                f"  {j + 1}. {snippet}\n     Source: {meta['title']} | confidence: {confidence:.3f}"
            )
    else:
        print("  No results found")
    print(f"Query time: {query_time:.0f} ms")
    print(f"\nErrors: {errors if errors else '[none]'}")
    print(f"\nEnd: {end_time.isoformat()}")
    print(f"Duration: {duration.seconds // 60} minutes {duration.seconds % 60} seconds")


if __name__ == "__main__":
    main()
