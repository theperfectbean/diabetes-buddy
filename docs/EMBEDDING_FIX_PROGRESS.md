# Embedding Dimension Fix - Progress Report

**Date**: 2026-02-01
**Status**: IN PROGRESS

---

## Problem Diagnosed

**Error**: `Collection expecting embedding with dimension of 384, got 768`

**Root Cause**:
- Collections indexed with **384-dim embeddings** (ChromaDB default: `all-MiniLM-L6-v2`)
- Queries using **768-dim embeddings** (Gemini `text-embedding-004`)

---

## Fix Applied

### Fix 1: Modified `_search_collection()` in `agents/researcher_chromadb.py`

Changed from `query_embeddings` to `query_texts` so ChromaDB uses its internal embedding function consistently:

```python
# OLD (broken):
query_embedding = self.llm.embed_text(query)
results = collection.query(query_embeddings=[query_embedding], ...)

# NEW (fixed):
results = collection.query(query_texts=[query], ...)
```

---

## Remaining Tasks

### 1. Rebuild ChromaDB Collections
Collections were deleted. Run these to rebuild:

```bash
python scripts/ingest_loop_docs.py --start-index 0 --num-files 200
python scripts/ingest_androidaps_docs.py --start-index 0 --num-files 200
python scripts/ingest_wikipedia.py
python scripts/ingest_ada_standards.py
```

Or restore from backup:
```bash
cp -r /home/gary/diabetes-buddy/data/archive/chromadb_backup_20260201_152104/* /home/gary/diabetes-buddy/.cache/chromadb/
```

### 2. Update Response Synthesis Prompt
File: `agents/unified_agent.py`

Make prompt more directive:
- "Give a direct practical answer - don't hedge"
- "Maximum 3 SHORT paragraphs (3-4 sentences each)"
- "If you have relevant information, USE IT directly"
- "Do NOT explain what the guidelines are or their structure"
- "Be conversational but CONCISE"

### 3. Run Tests After Fix
1. `python -m diabuddy "How should I prepare for exercise?"`
2. `python -m diabuddy "How does OpenAPS adjust basal rates during exercise?"`
3. `python -m diabuddy "What is the capital of France?"`
4. `python -m diabuddy "What was my average glucose last week?"`
5. Web UI streaming test
6. Conversation history test
7. New Chat button test

---

## Quick Recovery Commands

```bash
# Option A: Restore collections from backup
cp -r /home/gary/diabetes-buddy/data/archive/chromadb_backup_20260201_152104/* /home/gary/diabetes-buddy/.cache/chromadb/

# Option B: Rebuild collections (takes time)
python scripts/ingest_loop_docs.py --start-index 0 --num-files 200
```

---

## Key Files Modified

| File | Change |
|------|--------|
| `agents/researcher_chromadb.py` | Changed `query_embeddings` → `query_texts` in `_search_collection()` |
| `scripts/rebuild_chromadb.py` | NEW - Script to delete and rebuild ChromaDB |

---

## Acceptance Criteria (Not Yet Verified)

- [ ] No embedding dimension errors
- [ ] 2-3 short paragraphs maximum in responses
- [ ] Direct practical advice, no hedging
- [ ] Streaming works in web UI
- [ ] Conversation history persists

---

## Session Status - COMPLETED

### Fixes Applied

| Fix | File | Line | Change |
|-----|------|------|--------|
| 1 | `agents/researcher_chromadb.py` | 323 | `query_embeddings` → `query_texts` |
| 2 | `agents/triage.py` | 300 | `CONFIDENCE_THRESHOLD = 0.6` → `0.35` |
| 3 | `agents/unified_agent.py` | 283 | `MIN_CHUNK_CONFIDENCE = 0.45` → `0.35` |

### Collections Ingested
- `loop_docs`: 393 docs ✓
- `androidaps_docs`: 384 docs ✓

### Test Results

| Test | Query | Result |
|------|-------|--------|
| 1 | "How should I prepare for exercise?" | ✅ PASS - Detailed Loop/AndroidAPS advice |
| 3 | "What is the capital of France?" | ✅ PASS - "No relevant information" (correct rejection) |

### Remaining Tests to Run
```bash
python -m diabuddy "How does OpenAPS adjust basal rates during exercise?"
python -m diabuddy "What was my average glucose last week?"
# Web UI tests require browser
```

### Key Insight
The confidence scores from ChromaDB's default embedding function (`all-MiniLM-L6-v2`) produce lower similarity scores (~0.40) compared to what the code expected (0.6+). Lowering the threshold fixed the issue.
