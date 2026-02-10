# Phase 1 - Issue 1.1 Implementation Report

**Date**: February 6, 2026
**Commit**: `33da672`
**Reference**: ARCHITECTURE_AUDIT_REPORT_REFINED.md, Issue 1.1

---

## Problem

`search_multiple()` in `agents/researcher_chromadb.py` silently skipped sources not present in `search_map`. When the triage agent routed a query to an unmapped source (e.g., a new category added to `QueryCategory` but not yet wired into `search_map`), the method returned an empty dict for that source with no log output. This made it impossible to diagnose why queries returned no results.

### Failure chain before fix

1. `TriageAgent.classify()` routes query to a category (e.g., `USER_SOURCES`)
2. Category mapped to source string (e.g., `"user_sources"`)
3. `researcher.search_multiple(query, ["user_sources"])` called
4. If `"user_sources"` not in `search_map` at that moment, the `ThreadPoolExecutor` comprehension's `if source in search_map` filter silently excluded it
5. Caller received `{}` — the source key was entirely absent from the results dict
6. No log entry, no warning, no indication of what went wrong

---

## Fix Applied

**File**: `agents/researcher_chromadb.py`, lines 1426-1432

Added a pre-scan loop before the `ThreadPoolExecutor` block:

```python
for source in sources:
    if source not in search_map:
        logger.warning(
            f"Source '{source}' not in search_map. "
            f"Available sources: {list(search_map.keys())}"
        )
        results[source] = []
```

### What changed

| Aspect | Before | After |
|--------|--------|-------|
| Unmapped source logged | No | Yes (`logger.warning`) |
| Unmapped source in results dict | Key absent | Key present with `[]` |
| Mapped source behavior | Unchanged | Unchanged |
| Error on unmapped source | No | No (warning only) |

### What did NOT change

- The `ThreadPoolExecutor` block and its `if source in search_map` filter remain identical
- Mapped sources still execute in parallel as before
- Exception handling for individual search method failures is unchanged
- The `search_map` dictionary itself is unchanged

---

## Verification

### Test results

All tests pass except pre-existing failures unrelated to this change:

| Test | Result | Notes |
|------|--------|-------|
| All passing tests | Pass | No regressions |
| `test_practical_query_prioritizes_openaps` | Fail | Pre-existing (documented in MEMORY.md) |
| `test_openaps_content_quality` | Fail | Pre-existing (documented in MEMORY.md) |
| `test_search_multiple_includes_all_sources` | Fail | Pre-existing — references removed `search_theory` method |
| `test_sufficient_rag_quality` | Fail | Pre-existing quality metric threshold |

### Manual verification approach

To confirm the warning fires, call `search_multiple()` with an unmapped source:

```python
researcher.search_multiple("test query", ["nonexistent_source"])
# Expected log: WARNING - Source 'nonexistent_source' not in search_map. Available sources: [...]
# Expected return: {"nonexistent_source": []}
```

---

## Observations

### 1. The existing `search_map` already covers `user_sources`

The audit report's example scenario (USER_SOURCES routing failing because `"user_sources"` is missing from `search_map`) is not currently happening. The map at line 1421 includes `"user_sources": self.search_user_sources`. The silent-skip risk is real but latent — it would surface when new categories are added without updating `search_map`.

### 2. The `print()` on line 1446 should be `logger.error()`

Inside the executor's exception handler, errors are reported via `print()` rather than the logger:

```python
except Exception as e:
    print(f"Error searching {source}: {e}")
    results[source] = []
```

This is a separate issue (Issue 2.1 in the audit report) but worth noting as a related inconsistency in the same method.

### 3. `search_map` is rebuilt on every call

The map is defined inside `search_multiple()`, not at class or module level. This means it's reconstructed on every invocation. While functionally correct (it captures `self` method references), it duplicates the source-name-to-method mapping that other modules also need. This is Issue 1.5 in the audit report.

### 4. The `glooko_data` entry returns a lambda

```python
"glooko_data": lambda q: [],  # Placeholder - handled by GlookoQueryAgent
```

This means `glooko_data` is technically "mapped" but always returns empty results. It won't trigger the new warning, but callers still get no data. This is by design (Glooko queries go through a separate agent), but could be confusing without context.

---

## Remaining Phase 1 work

Per the audit report, Phase 1 has one more item:

| Issue | Description | Status | Effort |
|-------|-------------|--------|--------|
| 4.1 | Fix `debug_camaps_exercise.py` attribute names (`secondarycategories` / `synthesizedanswer`) | **False positive** — file already uses correct snake_case attributes | 0 min |
| 1.1 | Add logging to `search_multiple()` silent failures | **Done** | 15 min |

---

## Acceptance Criteria Status

- [x] Warning logged when source not in search_map
- [x] Warning includes list of valid sources
- [x] Empty list returned for unmapped source (not skip)
- [x] All existing tests pass (excluding pre-existing failures)
- [x] No change to successful query behavior
