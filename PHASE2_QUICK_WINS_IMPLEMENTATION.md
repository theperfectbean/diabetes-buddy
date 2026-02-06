# Phase 2 - Quick Wins Implementation Report

**Date**: February 6, 2026
**Commit**: `462333a`
**Reference**: ARCHITECTURE_AUDIT_REPORT_REFINED.md, Issues 1.2, 2.1, 5.2, 5.3

---

## Issue 1.2: Complete category_to_source mapping

### Problem

`QueryCategory` enum has 5 values but `_search_categories()` in `agents/triage.py` only mapped 3 of them in a local dict:

```python
category_to_source = {
    QueryCategory.CLINICAL_GUIDELINES: "clinical_guidelines",
    QueryCategory.KNOWLEDGE_BASE: "knowledge_base",
    QueryCategory.USER_SOURCES: "user_sources",
}
```

`GLOOKO_DATA` and `HYBRID` were handled by `if/elif` branches above the dict lookup, so they worked — but the incomplete mapping meant:
- Adding a new `QueryCategory` value could silently fall through all branches
- No compile-time or load-time check that every category was accounted for
- The mapping was local to `_search_categories()`, invisible to the rest of the codebase

### Fix Applied

**File**: `agents/triage.py`, lines 52-63

Added a module-level constant with all 5 categories mapped:

```python
CATEGORY_TO_SOURCE_MAP = {
    QueryCategory.GLOOKO_DATA: "glooko_data",
    QueryCategory.CLINICAL_GUIDELINES: "clinical_guidelines",
    QueryCategory.USER_SOURCES: "user_sources",
    QueryCategory.KNOWLEDGE_BASE: "knowledge_base",
    QueryCategory.HYBRID: ["clinical_guidelines", "user_sources", "knowledge_base"],
}

for _cat in QueryCategory:
    assert _cat in CATEGORY_TO_SOURCE_MAP, f"Missing mapping for {_cat}"
```

Updated `_search_categories()` (line ~435) to use `CATEGORY_TO_SOURCE_MAP` instead of the local dict. The `if/elif` chain for special cases (`HYBRID`, `KNOWLEDGE_BASE`, `USER_SOURCES`) is preserved, but now every category resolves through the map.

### What changed

| Aspect | Before | After |
|--------|--------|-------|
| Categories mapped | 3 of 5 (local dict) | 5 of 5 (module constant) |
| Load-time validation | None | `assert` for every `QueryCategory` value |
| GLOOKO_DATA in map | No (handled by early return) | Yes (`"glooko_data"`) |
| HYBRID in map | No (hardcoded in `if` branch) | Yes (`["clinical_guidelines", "user_sources", "knowledge_base"]`) |
| Routing behavior | Unchanged | Unchanged |

### What did NOT change

- The `GLOOKO_DATA` early-return at the top of `_search_categories()` still filters it out before the loop
- The `HYBRID` and `KNOWLEDGE_BASE` special-case branches still trigger `needs_knowledge_search`
- The `query_knowledge()` call for knowledge base searches is unchanged
- The `search_multiple()` call and result merging are unchanged

---

## Issue 2.1: Replace print() with logger in exception handlers

### Problem

Exception handlers across `agents/researcher_chromadb.py` used `print()` instead of the `logger` that was already imported and used elsewhere in the same file. This meant:
- Errors went to stdout, not the logging framework
- No log level, timestamp, or module context on error messages
- Log aggregation tools couldn't capture these errors
- In production (e.g., behind a web server), stdout may not be monitored

A related `print()` in `agents/triage.py` had the same issue.

### Fix Applied

**File**: `agents/researcher_chromadb.py` — 10 replacements

| Line | Method | Before | After |
|------|--------|--------|-------|
| 197 | `_extract_text()` | `print(f"Error extracting PDF text: {e}")` | `logger.exception(...)` |
| 242 | `_embed_batch()` | `print(f"Error embedding batch: {e}")` | `logger.exception(...)` |
| 340 | `_search_collection()` | `print(f"Warning: Collection '{source_key}' not found: {e}")` | `logger.warning(...)` |
| 350 | `_search_collection()` | `print(f"Error embedding query: {e}")` | `logger.exception(...)` |
| 365 | `_search_collection()` | `print(f"Error querying collection: {e}")` | `logger.exception(...)` |
| 657 | `search_ada_standards()` | `print(f"Error querying ada_standards collection: {e}")` | `logger.exception(...)` |
| 879 | `search_research_papers()` | `print(f"Error querying research papers collection: {e}")` | `logger.exception(...)` |
| 931 | `search_wikipedia_education()` | `print(f"Error querying wikipedia_education collection: {e}")` | `logger.exception(...)` |
| 1189 | `remove_source()` | `print(f"Warning: Could not delete collection {collection_key}: {e}")` | `logger.exception(...)` |
| 1446 | `search_multiple()` | `print(f"Error searching {source}: {e}")` | `logger.exception(...)` |

**File**: `agents/triage.py` — 1 replacement

| Line | Method | Before | After |
|------|--------|--------|-------|
| 474 | `_search_categories()` | `print(f"Warning: Knowledge base search failed: {e}")` | `logger.exception(...)` |

### What did NOT change

- The `print()` statements in the `if __name__ == "__main__"` block at the bottom of `researcher_chromadb.py` (line 1555) — these are CLI test output, not error handling
- The exception handling logic itself (catch, return `[]`, retry behavior) is unchanged
- `logger.warning()` used for "not found" cases; `logger.exception()` used for unexpected errors (includes stack trace)

---

## Issue 5.2: Make ChromaDB path configurable

### Problem

The ChromaDB storage path was derived from the project root with no override mechanism:

```python
self.db_path = self.project_root / ".cache" / "chromadb"
```

This made it impossible to:
- Use a different storage location in CI/CD or testing
- Share a ChromaDB instance across multiple project checkouts
- Place the database on a faster filesystem

### Fix Applied

**File**: `agents/researcher_chromadb.py`, lines 92-98

```python
# Initialize ChromaDB (path configurable via CHROMADB_PATH env var)
chromadb_env = os.getenv("CHROMADB_PATH")
if chromadb_env:
    self.db_path = Path(chromadb_env)
else:
    self.db_path = self.project_root / ".cache" / "chromadb"
self.db_path.mkdir(parents=True, exist_ok=True)
```

**File**: `README.md`, Environment Variables section

Added: `CHROMADB_PATH=/custom/chromadb   # ChromaDB storage path (default: .cache/chromadb)`

### What changed

| Aspect | Before | After |
|--------|--------|-------|
| Default path | `.cache/chromadb` (relative to project root) | Same default |
| Override mechanism | None | `CHROMADB_PATH` env var |
| Directory creation | `mkdir(parents=True, exist_ok=True)` | Unchanged |
| Documentation | Not mentioned | Documented in README.md |

### Verification

```bash
CHROMADB_PATH=/tmp/test_db python -c "
from agents.researcher_chromadb import ChromaDBBackend
b = ChromaDBBackend()
print(b.db_path)  # /tmp/test_db
"
```

---

## Issue 5.3: Make embedding model configurable

### Problem

The embedding model was hardcoded (via `LOCAL_EMBEDDING_MODEL` env var with default `all-mpnet-base-v2`) in `agents/llm_provider.py`. The env var name was non-obvious and undocumented.

```python
model_name = os.environ.get("LOCAL_EMBEDDING_MODEL", "all-mpnet-base-v2")
```

### Fix Applied

**File**: `agents/llm_provider.py`, line 647

Added `EMBEDDING_MODEL` as the primary env var with `LOCAL_EMBEDDING_MODEL` as a backward-compatible fallback:

```python
model_name = os.environ.get(
    "EMBEDDING_MODEL",
    os.environ.get("LOCAL_EMBEDDING_MODEL", "all-mpnet-base-v2"),
)
```

**File**: `README.md`, Environment Variables section

Added: `EMBEDDING_MODEL=all-mpnet-base-v2  # Sentence transformer model for embeddings`

### What changed

| Aspect | Before | After |
|--------|--------|-------|
| Primary env var | `LOCAL_EMBEDDING_MODEL` | `EMBEDDING_MODEL` |
| Backward compat | N/A | `LOCAL_EMBEDDING_MODEL` still works as fallback |
| Default model | `all-mpnet-base-v2` | Unchanged |
| Documentation | Not mentioned | Documented in README.md |

### Resolution order

1. `EMBEDDING_MODEL` (if set)
2. `LOCAL_EMBEDDING_MODEL` (if set, backward compat)
3. `all-mpnet-base-v2` (default)

---

## Verification

### Test results

All tests pass except pre-existing failures unrelated to these changes:

| Test Suite | Result | Notes |
|------------|--------|-------|
| `test_chromadb_integration.py` | 13 passed, 3 failed | Pre-existing failures (documented in MEMORY.md) |
| `test_e2e_hybrid.py` | 4 passed, 3 failed | Pre-existing failures (verified identical on master) |
| `test_hybrid_knowledge.py` | 23 passed, 5 failed | Pre-existing failures (verified identical on master) |
| `test_llm_provider.py` | 1 passed | No regressions |
| Module import validation | Pass | `CATEGORY_TO_SOURCE_MAP` assert passes on load |

### Pre-existing failures confirmed on master

The following failures were verified to exist identically before and after the changes by running `git stash` and testing on clean master:

- `test_practical_query_prioritizes_openaps`
- `test_openaps_content_quality`
- `test_sufficient_rag_quality`
- `test_e2e_insulin_timing_sparse_rag`
- `test_e2e_obscure_topic`
- `test_e2e_emergency_query`
- `test_hybrid_prompt_contains_rag_context`
- `test_hybrid_prompt_attribution_instructions`
- `test_hybrid_prompt_prohibition_rules`
- `test_hybrid_prompt_priority_order`
- `test_hybrid_prompt_with_glooko`

---

## Files Modified

| File | Changes |
|------|---------|
| `agents/triage.py` | +21 lines, -13 lines — `CATEGORY_TO_SOURCE_MAP` constant, validation assert, updated `_search_categories()`, `print()` → `logger.exception()` |
| `agents/researcher_chromadb.py` | +19 lines, -12 lines — 10 `print()` → `logger` replacements, `CHROMADB_PATH` env var support |
| `agents/llm_provider.py` | +4 lines, -1 line — `EMBEDDING_MODEL` env var with fallback |
| `README.md` | +2 lines — Documented `CHROMADB_PATH` and `EMBEDDING_MODEL` env vars |

---

## Remaining Phase 2 work

Per the audit report, Phase 2 has 2 more items not addressed in this batch:

| Issue | Description | Status | Effort |
|-------|-------------|--------|--------|
| 1.2 | Complete category_to_source mapping | **Done** | 20 min |
| 2.1 | Add logging to search method exceptions | **Done** | 20 min |
| 5.2 | Make ChromaDB path configurable | **Done** | 10 min |
| 5.3 | Make embedding model configurable | **Done** | 20 min |
| 1.5 | Extract `search_map` to class-level constant | Not started | 15 min |
| 2.2 | Add structured error responses | Not started | 30 min |

---

## Acceptance Criteria Status

- [x] All 5 QueryCategory values mapped in CATEGORY_TO_SOURCE_MAP
- [x] Validation asserts all categories are mapped
- [x] All search method exceptions use logger.exception() not print()
- [x] CHROMADB_PATH environment variable respected
- [x] EMBEDDING_MODEL environment variable respected
- [x] README.md documents both new env vars
- [x] All existing tests pass (excluding pre-existing failures)
