# Citation Metadata Fix - Implementation Report

**Date**: February 6, 2026
**Version**: v0.2.3
**File**: `agents/unified_agent.py`

---

## Problem

Synthesized answers contained generic `[Source limitation]` tags instead of proper page-level citations like `[CamAPS FX Manual, p.46]`.

Debug output showed:
```
Source: Camaps Fx    ✓
Page: N/A            ✗
Metadata: N/A        ✗
```

## Root Cause Analysis

The initial diagnosis (from `PHASE2_QUICK_WINS_IMPLEMENTATION.md`) pointed at `search_user_sources()` not populating `SearchResult.page_number`. This was **incorrect**.

### What was actually working

`_search_collection()` in `agents/researcher_chromadb.py:414-420` already correctly extracts page numbers:

```python
search_results.append(SearchResult(
    quote=doc,
    page_number=metadata.get('page'),  # ← Already populated
    confidence=confidence,
    source=source_name,
    context=context
))
```

### What was actually broken

Two downstream formatting methods in `agents/unified_agent.py` discarded the page data before it reached the LLM:

| Method | Problem |
|--------|---------|
| `_search_knowledge_base()` | Context stripped all metadata: `f"---\n{r.quote[:600]}\n\n"` |
| `_format_sources_for_citation()` | Deduplicated by source name only, losing page granularity |

Additionally, `debug_citations.py` checked wrong attribute names (`result.page` instead of `result.page_number`, `result.metadata` instead of `result.context`), giving false "N/A" readings.

## Fix Applied

### 1. `_search_knowledge_base()` - Add source attribution to context chunks

**File**: `agents/unified_agent.py`, line ~1362

| Before | After |
|--------|-------|
| `f"---\n{r.quote[:600]}\n\n"` | `f"---\n[Source: {r.source}{page_info}]\n{r.quote[:600]}\n\n"` |

The LLM now sees which source and page each chunk came from:

```
---
[Source: CamAPS FX Manual, p.46]
Ease-off is a feature that reduces insulin delivery...
```

Note: The existing `_clean_response()` method already strips `[Source: ...]` patterns from the LLM *output* (line ~2189), so these tags won't leak into user-facing responses.

### 2. `_format_sources_for_citation()` - Per-page source entries

**File**: `agents/unified_agent.py`, line ~1449

| Before | After |
|--------|-------|
| Deduplicated by `source_name` only | Deduplicated by `(source_name, page_number)` tuple |
| `[1] CamAPS FX Manual` | `[1] CamAPS FX Manual, p.46` |
| One entry per source | One entry per source+page |

The LLM source list now reads:

```
=== RETRIEVED SOURCES (CITE BY NUMBER [1], [2], etc.) ===
[1] CamAPS FX Manual, p.46
[2] CamAPS FX Manual, p.47
[3] ADA Standards of Care 2026
=== END SOURCES ===
```

### 3. `debug_citations.py` - Correct attribute names

| Before | After |
|--------|-------|
| `result.page` | `result.page_number` |
| `result.metadata` | `result.context` |

## What did NOT change

- `SearchResult` dataclass - unchanged, already had `page_number: Optional[int]`
- `_search_collection()` - unchanged, already extracted page from ChromaDB metadata
- `search_user_sources()` - unchanged, correctly delegates to `_search_collection()`
- `_clean_response()` - unchanged, already strips `[Source: ...]` from LLM output
- Citation prompt instructions - unchanged, LLM still uses `[1]`, `[2]` format

## Expected Outcome

**Before:**
```
[Source limitation] [Source limitation]
```

**After:**
```
Ease-off mode helps reduce insulin delivery [1]. You should activate it
60-90 minutes before exercise [2].

[1] CamAPS FX Manual, p.46
[2] CamAPS FX Manual, p.47
```

## 4. Groq reasoning model resilience

**File**: `agents/llm_provider.py`

The `gpt-oss-20b` reasoning model sometimes returns all output in the `reasoning` field with an empty `content` field. This caused `"Groq failed after 3 attempts"` errors.

### Non-streaming (`generate_text`, line ~517)

| Before | After |
|--------|-------|
| Empty content → raise `LLMProviderError` | Empty content → check `reasoning` field → return it as fallback |

### Streaming (`generate_text_stream`, line ~596)

| Before | After |
|--------|-------|
| Reasoning chunks silently discarded | Reasoning chunks buffered; yielded as fallback if no content arrives |

The unified agent's main synthesis path uses `generate_text` (non-streaming) via `_generate_with_fallback`, so this fix directly prevents the crash the user experienced.

## Testing

- All existing tests pass (only pre-existing failures: `test_practical_query_prioritizes_openaps`, `test_openaps_content_quality`)
- No test regressions introduced
- Verify with: `python debug_citations.py`
