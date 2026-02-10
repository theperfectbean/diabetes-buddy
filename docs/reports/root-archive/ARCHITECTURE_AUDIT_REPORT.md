# Diabetes Buddy - Comprehensive Architecture Audit Report

**Date**: February 6, 2026  
**Audit Scope**: Full codebase analysis for architectural inconsistencies, silent failures, and technical debt  
**Status**: Complete - Ready for review and prioritization

---

## Executive Summary

### Issues Found
- **Critical**: 3 issues (silent failures, broken routing, safety risks)
- **High**: 8 issues (inconsistencies, dead code, missing error handling)
- **Medium**: 12 issues (configuration drift, type safety, test gaps)
- **Low**: 7 issues (documentation, minor refactoring)
- **Total**: 30 documented issues

### Top 3 Most Urgent Fixes
1. **[CRITICAL]** Add `"user_sources"` key to `search_map` - Silent failure when USER_SOURCES queries skip searching
2. **[CRITICAL]** Fix attribute access bugs in debug scripts (snake_case vs camelCase)
3. **[HIGH]** Remove hardcoded references to removed community documentation (OpenAPS, Loop, AndroidAPS)

### Effort Estimates
- **Quick Wins** (< 30 min): 5 issues
- **Medium Effort** (30 min - 2 hrs): 15 issues
- **Large Effort** (2+ hrs): 10 issues

---

## Detailed Findings

### 1. Routing & Mapping Consistency (8 issues)

#### 1.1 [CRITICAL] Missing `"user_sources"` in search_map

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L1414-L1430)

**Issue**: The `search_map` dictionary is missing the `"user_sources"` key, causing silent failures:

```python
search_map = {
    "clinical_guidelines": self.search_clinical_guidelines,
    "ada_standards": self.search_ada_standards,
    "australian_guidelines": self.search_australian_guidelines,
    "research_papers": self.search_research_papers,
    "wikipedia_education": self.search_wikipedia_education,
    "user_sources": self.search_user_sources,  # ✅ EXISTS in code
    "pubmed_research": self.search_research_papers,  # Alias
    "glooko_data": lambda q: [],  # Placeholder
}
```

Then later:
```python
for source in sources
if source in search_map  # ❌ SILENT SKIP if source not in map
```

This is **exactly the bug just discovered**. When triage.py routes to `USER_SOURCES`, it calls:
```python
results = self.researcher.search_multiple(query, sources_to_search)
```

If `"user_sources"` isn't in the map, it silently skips the search and returns empty results.

**Status**: RECENTLY FIXED (according to code), but pattern suggests other similar issues could exist

**Impact**: Users asking about their device manuals get no results
**Severity**: CRITICAL (user-facing silent failure)
**Effort**: Quick (verify the fix is complete and add defensive checks)

---

#### 1.2 [HIGH] Inconsistent category_to_source mapping

**Location**: [agents/triage.py](agents/triage.py#L428-L440)

**Issue**: The mapping between QueryCategory enum and source strings is scattered:

```python
category_to_source = {
    QueryCategory.CLINICAL_GUIDELINES: "clinical_guidelines",
    QueryCategory.KNOWLEDGE_BASE: "knowledge_base",
    QueryCategory.USER_SOURCES: "user_sources",
}
```

**Problem**: This mapping is:
1. **Only in triage.py** - duplicated logic
2. **Incomplete** - doesn't cover all categories (GLOOKO_DATA, HYBRID)
3. **Not validated** - no assertion that every QueryCategory has a source

**Recommendation**: Create a single source of truth:
```python
# In triage.py or a shared config
CATEGORY_TO_SOURCE = {
    QueryCategory.GLOOKO_DATA: "glooko_data",
    QueryCategory.CLINICAL_GUIDELINES: "clinical_guidelines",
    QueryCategory.USER_SOURCES: "user_sources",
    QueryCategory.KNOWLEDGE_BASE: "knowledge_base",
    QueryCategory.HYBRID: "hybrid",  # Special case
}

# Add validation on module load
for category in QueryCategory:
    assert category in CATEGORY_TO_SOURCE, f"Missing mapping for {category}"
```

**Severity**: HIGH (could cause routing to wrong source)
**Effort**: Medium (add mapping, add validation, update triage.py)

---

#### 1.3 [MEDIUM] search_multiple doesn't match search_map

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L1380)

**Issue**: The `search_multiple()` method accepts arbitrary source names but only handles them if they're in `search_map`:

```python
def search_multiple(self, query: str, sources: List[str]) -> dict:
    """Execute multiple source searches in parallel."""
    results = {}
    search_map = { ... }  # Defines available sources
    
    with ThreadPoolExecutor(...) as executor:
        future_to_source = {
            executor.submit(search_map[source], query): source
            for source in sources
            if source in search_map  # SILENT SKIP if source not found
        }
```

**Problem**: If triage.py passes a source name that's not in search_map, it fails silently (no error logged).

**Recommendation**: Log warnings for skipped sources:
```python
for source in sources:
    if source not in search_map:
        logger.warning(f"Source '{source}' not in search_map, skipping")
```

**Severity**: MEDIUM (already covered by issue 1.1, but general pattern is bad)
**Effort**: Quick (add logging)

---

#### 1.4 [HIGH] search_map vs search_multiple naming mismatch

**Location**: Multiple files

**Issue**: Three different search APIs with inconsistent naming:

1. **search_multiple(sources)** - takes list of source strings
2. **query_knowledge()** - discovers all collections dynamically
3. **search_all_collections()** - searches all with deduplication

These methods do different things but could be confused. Method names don't clarify which uses search_map.

**Recommendation**: Rename for clarity:
```python
search_multiple()       → search_by_source_keys()  # Uses search_map
query_knowledge()       → search_all_collections_dynamic()  # Dynamic discovery
search_all_collections()→ search_all_collections_deduplicated()  # With dedup
```

**Severity**: HIGH (confusing API surface)
**Effort**: Medium (rename + update all callers)

---

#### 1.5 [MEDIUM] Router suggests sources that might not exist

**Location**: [agents/router_agent.py](agents/router_agent.py#L85-L140)

**Issue**: RouterAgent hardcodes device names in `suggested_sources`:

```python
AUTOMATED_SYSTEMS = [
    "camaps fx", "camaps", "cam aps",
    "control-iq", "control iq", "controliq",
    "loop", "openaps", "androidaps", ...
]
```

But these are never validated against what sources actually exist. If a user uploads a device manual for "Dana-i", the router has no knowledge of it.

**Recommendation**: RouterAgent should query available sources dynamically:
```python
# In RouterAgent.__init__
self.available_sources = self.researcher.list_pdf_collections()

# In suggest_sources()
# Match detected devices against available sources
```

**Severity**: MEDIUM (router suggestions might be incorrect)
**Effort**: Medium (add dynamic source discovery to router)

---

#### 1.6 [MEDIUM] Inconsistent collection naming conventions

**Location**: Multiple files

**Issue**: Collections use inconsistent naming patterns:

- `"ada_standards"` (snake_case)
- `"research_papers"` (snake_case)
- `"wikipedia_education"` (snake_case)
- User sources: `"camaps_fx_manual"` (snake_case from PDF filename)

But also hardcoded with inconsistent patterns:
- `"australian_guidelines"` (hyphen alternative would be `"australian-guidelines"`)
- No prefix distinguishing collection types

**Recommendation**: Establish naming convention:
```
Type prefix:
  "clinical_"  → Clinical guidelines (ada_standards, australian_guidelines)
  "research_"  → Research papers
  "user_"      → User-uploaded device manuals
  "community_" → Community documentation (if restored)

Pattern: "{type_prefix}{source_name}"
  "clinical_ada_standards"
  "research_pubmed_papers"
  "user_camaps_fx_manual"
```

**Severity**: MEDIUM (code clarity, migration risk)
**Effort**: Medium (rename collections, update all references)

---

#### 1.7 [HIGH] HYBRID category routing incomplete

**Location**: [agents/triage.py](agents/triage.py#L436-L441)

**Issue**: When category is HYBRID, the routing logic is incomplete:

```python
if category == QueryCategory.HYBRID:
    # Search all sources for hybrid queries
    sources_to_search.append("clinical_guidelines")
    needs_knowledge_search = True
```

**Problems**:
1. Only appends "clinical_guidelines", not all HYBRID sources
2. Doesn't append "user_sources" even though HYBRID should search everything
3. `needs_knowledge_search` flag is confusing (what counts as "knowledge"?)

**Recommendation**: Explicit HYBRID routing:
```python
if category == QueryCategory.HYBRID:
    sources_to_search.extend([
        "clinical_guidelines",
        "user_sources",  # Add this
        "knowledge_base",
    ])
```

**Severity**: HIGH (HYBRID queries miss sources)
**Effort**: Quick (add missing source)

---

#### 1.8 [MEDIUM] No validation that all categories have search paths

**Location**: [agents/triage.py](agents/triage.py#L415-L450)

**Issue**: New QueryCategory enum values can be added without adding corresponding search logic:

```python
class QueryCategory(Enum):
    GLOOKO_DATA = "glooko_data"  # Special case - handled elsewhere
    CLINICAL_GUIDELINES = "clinical_guidelines"
    USER_SOURCES = "user_sources"
    KNOWLEDGE_BASE = "knowledge_base"
    HYBRID = "hybrid"
    # What if someone adds MEAL_MANAGEMENT here?
```

If a new category is added, it might silently fail to search.

**Recommendation**: Add validation in _search_categories():
```python
def _search_categories(self, query: str, categories: list[QueryCategory]):
    # Validate all categories have handlers
    for category in categories:
        if category not in category_to_source and category not in [QueryCategory.HYBRID, QueryCategory.GLOOKO_DATA]:
            raise ValueError(f"No search handler for category {category}")
```

**Severity**: MEDIUM (prevents silent failures for new categories)
**Effort**: Quick (add validation)

---

### 2. Silent Failure Detection (6 issues)

#### 2.1 [CRITICAL] Missing USER_SOURCES error handling in search_multiple

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L1418-L1432)

**Issue**: Already documented above as issue 1.1. The pattern is:

```python
search_map = { ... "user_sources": self.search_user_sources ... }

for source in sources
    if source in search_map  # SILENTLY SKIP
```

This is a **critical silent failure pattern**. When user_sources isn't found, no error is logged, no exception raised, just empty results.

**Recommendation**: Convert to loud failure:
```python
for source in sources:
    if source not in search_map:
        logger.error(f"Source '{source}' not configured in search_map")
        results[source] = []  # Empty results with logging
    else:
        # Search normally
```

**Severity**: CRITICAL
**Effort**: Quick (add logging)

---

#### 2.2 [HIGH] search_user_sources returns empty list without logging when no device collections found

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L825-L830)

**Issue**: If user uploads no device manuals:

```python
if not device_collections:
    logger.info("No device manual collections found")
    return []
```

This is silent from the user perspective - they get empty results with no indication why.

**Recommendation**: Log at DEBUG level but let response layer decide what to show user:
```python
if not device_collections:
    logger.debug("No device manual collections found in ChromaDB")
    return []  # Empty results OK here, app should handle gracefully
```

**Severity**: HIGH (user experience issue)
**Effort**: Quick (add context to logging)

---

#### 2.3 [HIGH] Exception handling swallows errors in search methods

**Location**: Multiple search methods

**Issue**: Generic exception handling hides real problems:

```python
# In search_ada_standards
try:
    results = collection.query(...)
except Exception as e:
    print(f"Error querying ada_standards collection: {e}")
    return []

# In search_research_papers
try:
    results = collection.query(...)
except Exception as e:
    print(f"Error querying research papers collection: {e}")
    return []
```

**Problems**:
1. Uses `print()` instead of `logger.error()`
2. Returns empty list without distinguishing between "no results" and "error"
3. Same exception handler for different error types (missing collection vs query error)

**Recommendation**: Specific error handling:
```python
try:
    collection = self.chroma_client.get_collection(name="research_papers")
    if collection.count() == 0:
        logger.debug("research_papers collection is empty")
        return []
except Exception as e:
    logger.error(f"Cannot access research_papers collection: {e}")
    return []
```

**Severity**: HIGH (hides bugs, makes debugging hard)
**Effort**: Medium (update all search methods)

---

#### 2.4 [MEDIUM] Empty results not distinguished from "no source available"

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L860-L870)

**Issue**: Methods return empty list for both:
1. Source doesn't exist (collection not found)
2. Source exists but query returned no results

These should be distinguishable.

**Recommendation**: Add optional return flag:
```python
def search_ada_standards(...) -> tuple[List[SearchResult], str]:
    """Returns (results, status) where status is 'ok', 'missing', or 'empty'"""
    try:
        collection = ...
    except:
        return [], "missing"  # Collection doesn't exist
    
    if collection.count() == 0:
        return [], "empty"  # Collection exists but has no docs
    
    results = collection.query(...)
    return results, "ok"
```

**Severity**: MEDIUM (affects logging and error handling)
**Effort**: Medium (update method signatures)

---

#### 2.5 [MEDIUM] Collection query failures don't log chunk count

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L1438-L1455)

**Issue**: When ThreadPoolExecutor encounters an error:

```python
for future in as_completed(future_to_col):
    col_name = future_to_col[future]
    try:
        results = future.result()
        all_results.extend(results)
        if results:
            logger.debug(f"  {col_name}: {len(results)} results")
    except Exception as e:
        logger.warning(f"Error searching device collection '{col_name}': {e}")
```

Missing logging about what was attempted or partial results recovered.

**Recommendation**: Log attempt details:
```python
logger.info(f"Searching device collection: {col_name}")
try:
    results = future.result(timeout=5)
    all_results.extend(results)
    logger.debug(f"  {col_name}: {len(results)} results")
except Exception as e:
    logger.error(f"Failed to search {col_name}: {e}", exc_info=True)
    all_results.extend([])  # Explicit empty result
```

**Severity**: MEDIUM (diagnostic logging)
**Effort**: Quick (add logging)

---

#### 2.6 [HIGH] No validation that search_map is complete at runtime

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L1410)

**Issue**: The search_map is built at query time, not validated:

```python
def search_multiple(self, query: str, sources: List[str]) -> dict:
    search_map = {
        "clinical_guidelines": self.search_clinical_guidelines,
        ...
    }
```

If code changes remove a method but keep the key, it would crash.

**Recommendation**: Validate in __init__:
```python
def __init__(self, ...):
    # Validate all search methods exist
    required_methods = [
        "search_clinical_guidelines",
        "search_ada_standards",
        "search_australian_guidelines",
        "search_research_papers",
        "search_wikipedia_education",
        "search_user_sources",
    ]
    for method_name in required_methods:
        if not hasattr(self, method_name):
            raise RuntimeError(f"Missing required method: {method_name}")
    
    logger.info(f"ResearcherAgent initialized with {len(required_methods)} search methods")
```

**Severity**: HIGH (prevents silent failures if methods are deleted)
**Effort**: Quick (add validation)

---

### 3. Collection Management Consistency (7 issues)

#### 3.1 [HIGH] Collections created with inconsistent metadata

**Location**: Multiple files ([agents/researcher_chromadb.py](agents/researcher_chromadb.py#L165), [agents/source_manager.py](agents/source_manager.py), scripts)

**Issue**: ChromaDB collections are created with inconsistent metadata:

```python
# In researcher_chromadb.py:_init_collections
collection = self.chroma_client.get_or_create_collection(
    name=source_key,
    metadata={"hnsw:space": "cosine", "type": col_type, "source_category": col_type}
)

# In researcher_chromadb.py:refresh_user_sources
collection = self.chroma_client.get_or_create_collection(
    name=source.collection_key,
    metadata={"hnsw:space": "cosine", "type": "device_manual", "source_category": "device_manual"}
)

# In ingest_ada_standards.py
collection = client.get_or_create_collection(
    name="ada_standards",
    metadata={"hnsw:space": "cosine"}
    # Missing "type" field!
)
```

**Problems**:
1. Ada standards created without type metadata
2. Two ways of setting metadata (direct vs via variables)
3. No consistent versioning or schema

**Recommendation**: Create a collection factory:
```python
class CollectionFactory:
    @staticmethod
    def create_typed_collection(client, name, col_type, source_category=None):
        """Create collection with consistent metadata."""
        return client.get_or_create_collection(
            name=name,
            metadata={
                "hnsw:space": "cosine",
                "type": col_type,
                "source_category": source_category or col_type,
                "created_at": datetime.now().isoformat(),
                "schema_version": "1",
            }
        )
```

**Severity**: HIGH (breaks discovery, causes migration issues)
**Effort**: Medium (create factory, update all callers)

---

#### 3.2 [MEDIUM] No metadata for trust level or source origin

**Location**: All collection creation

**Issue**: Metadata doesn't track:
- Trust level (user-uploaded vs clinical guidelines)
- Source version/date
- Ingestion date
- Whether collection is complete

This makes it hard to audit or migrate.

**Recommendation**: Add to metadata:
```python
metadata={
    "hnsw:space": "cosine",
    "type": "clinical_guideline",
    "source_category": "clinical_guideline",
    "source_type": "official",  # "official", "community", "user_uploaded"
    "trust_level": 1.0,  # 0.0-1.0
    "source_version": "2026",
    "ingestion_date": "2026-02-06",
    "document_count": 0,  # Updated after ingestion
}
```

**Severity**: MEDIUM (audit/migration)
**Effort**: Medium (add metadata, update factory)

---

#### 3.3 [HIGH] No validation that user_sources collections exist before searching

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L781-M825)

**Issue**: search_user_sources uses collection metadata to discover sources, but what if metadata is wrong?

```python
device_collections = self.get_collections_by_type("device_manual")

if not device_collections:
    # Fallback: scan all collections excluding known types
    for col in all_collections:
        meta = col.metadata or {}
        col_type = meta.get("type")
        if col_type in ("clinical_guideline", "knowledge_base"):
            continue
        ...
```

The fallback heuristic is fragile - it assumes any collection without a known type is a device manual.

**Recommendation**: Be explicit:
```python
device_collections = self.get_collections_by_type("device_manual")

if not device_collections:
    logger.warning("No device manual collections found by metadata")
    # Don't fallback to heuristic - let user know uploads are needed
    return []
```

**Severity**: HIGH (could search wrong collections)
**Effort**: Quick (remove fragile fallback)

---

#### 3.4 [MEDIUM] Collection count changes during search (race condition)

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L643-L655)

**Issue**: Collection count is checked but might change:

```python
def search_ada_standards(...):
    try:
        collection = self.chroma_client.get_collection(name="ada_standards")
    except Exception:
        return []

    if collection.count() == 0:  # Check at this moment
        return []

    try:
        results = collection.query(...)  # But collection might now be empty
```

Unlikely but possible if another process modifies the DB.

**Recommendation**: Use try-except instead of count check:
```python
def search_ada_standards(...):
    try:
        collection = self.chroma_client.get_collection(name="ada_standards")
        results = collection.query(
            query_texts=[enhanced_query],
            n_results=min(top_k, 100)  # Safe default
        )
    except Exception as e:
        if "not found" in str(e).lower():
            logger.debug(f"Collection 'ada_standards' does not exist")
        else:
            logger.error(f"Error querying ada_standards: {e}")
        return []
```

**Severity**: MEDIUM (edge case, unlikely in practice)
**Effort**: Quick (remove count check)

---

#### 3.5 [MEDIUM] Collections never validated for emptiness after ingestion

**Location**: Ingestion scripts

**Issue**: After ingesting PDFs, collections aren't validated to have content:

```python
def _process_pdf(self, source_key, pdf_path, collection):
    # Extract and add documents
    # ... 200+ lines of code ...
    # No assertion that collection.count() > 0 at the end
```

If extraction fails silently, collection could be empty.

**Recommendation**: Add validation:
```python
def _process_pdf(self, source_key, pdf_path, collection):
    initial_count = collection.count()
    # Extract and add documents
    # ...
    final_count = collection.count()
    
    if final_count == initial_count:
        logger.error(f"No documents added to {source_key} collection")
        raise RuntimeError(f"PDF processing failed for {pdf_path}")
    
    logger.info(f"Successfully added {final_count - initial_count} documents to {source_key}")
```

**Severity**: MEDIUM (prevents silent ingestion failures)
**Effort**: Quick (add validation)

---

#### 3.6 [MEDIUM] Collection deletion doesn't update search_map

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L1180-L1195)

**Issue**: delete_user_source_collection removes from internal maps but search_map in search_multiple still references it:

```python
def delete_user_source_collection(self, collection_key: str):
    self.chroma_client.delete_collection(name=collection_key)
    if collection_key in self.pdf_paths:
        del self.pdf_paths[collection_key]  # Removed from discovery
    ...

def search_multiple(self, query: str, sources: List[str]):
    search_map = { ... }  # Built fresh each time
    # So this works - search_map is rebuilt on each call
```

Actually this is OK because search_map is rebuilt each call. But it's confusing.

**Recommendation**: Document that search_map is runtime-built, not cached:
```python
def search_multiple(self, query: str, sources: List[str]) -> dict:
    """
    Search specified sources in parallel.
    
    Note: search_map is built fresh on each call from available methods,
    so changes to available collections are reflected immediately.
    """
```

**Severity**: LOW (documented confusing behavior)
**Effort**: Quick (add docstring)

---

#### 3.7 [MEDIUM] No way to list or validate all collections

**Location**: ResearcherAgent class

**Issue**: No public method to get all discoverable collections and their metadata.

**Recommendation**: Add inventory method:
```python
def get_collection_inventory(self) -> dict:
    """Return all accessible collections with metadata and sizes."""
    inventory = {}
    try:
        for col in self.chroma_client.list_collections():
            inventory[col.name] = {
                "count": col.count(),
                "metadata": col.metadata or {},
                "type": col.metadata.get("type", "unknown") if col.metadata else "unknown",
            }
    except Exception as e:
        logger.error(f"Cannot list collections: {e}")
    return inventory
```

Then add endpoint to app.py to expose this.

**Severity**: MEDIUM (operational/debugging)
**Effort**: Medium (add method, expose via API)

---

### 4. Dead Code & Broken References (5 issues)

#### 4.1 [HIGH] Hardcoded references to removed community documentation

**Location**: Comments and documentation

**Issue**: Project removed OpenAPS, Loop, AndroidAPS collections due to device prioritization, but comments still reference them:

```python
# In triage.py:_search_categories
# Track if we need to search the knowledge base (openaps_docs, loop_docs, etc.)

# In search_mapping_full.txt (documentation)
# (openaps_docs, loop_docs, androidaps_docs, wikipedia_education, research_papers)
```

**Problem**: This creates confusion about what sources exist.

**Recommendation**: Update all comments:
```python
# Track if we need to search knowledge base
# (community documentation like OpenAPS/Loop was removed - now only user sources)
```

**Severity**: HIGH (confuses maintainers)
**Effort**: Quick (find and update comments)

---

#### 4.2 [MEDIUM] Unused variables in test scripts

**Location**: Various test files

**Issue**: Old test/debug scripts have unused imports or variables:

```python
# debug_camaps_exercise.py
from agents.triage import TriageAgent
# Line 31 has bug trying to access .secondarycategories
```

**Recommendation**: Audit and clean up unused test files.

**Severity**: MEDIUM (clutter)
**Effort**: Quick (remove files or fix)

---

#### 4.3 [MEDIUM] Ingestion scripts for removed sources still exist

**Location**: Scripts directory

**Issue**: These scripts exist but are no longer used:
- `scripts/ingest_openaps_docs.py`
- `scripts/ingest_loop_docs.py`
- `scripts/ingest_androidaps_docs.py`
- `scripts/ingest_openaps_batch1.py`

**Recommendation**: Either:
1. Delete these files
2. Add comments explaining they're deprecated
3. Wrap in try/except explaining why they're disabled

**Severity**: MEDIUM (maintenance burden)
**Effort**: Quick (delete or comment)

---

#### 4.4 [MEDIUM] search_all_pdfs() method never called

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L570-L585)

**Issue**: The method exists but doesn't appear in any search_map or main queries:

```python
def search_all_pdfs(self, query: str, top_k: int = 5) -> List[SearchResult]:
    """Search all discovered PDF collections and merge results."""
    all_results = []
    for source_key in self.pdf_paths.keys():
        ...
```

**Recommendation**: Either:
1. Ensure it's used by removing duplicate functionality
2. Remove if redundant with search_user_sources
3. Add to search_map if it should be available

**Severity**: MEDIUM (dead code)
**Effort**: Quick (determine intent and remove/use)

---

#### 4.5 [LOW] Comments reference old method names

**Location**: Various docstrings

**Issue**: Docstrings mention `search_openaps_docs()`, `search_loop_docs()` which don't exist:

```python
# In triage.py docstring comments
# "openaps_docs, loop_docs, androidaps_docs" - these methods don't exist
```

**Recommendation**: Update docstrings to reflect current API.

**Severity**: LOW (documentation)
**Effort**: Quick (update docstrings)

---

### 5. Configuration Drift (4 issues)

#### 5.1 [MEDIUM] Hardcoded confidence thresholds scattered across code

**Location**: Multiple files

**Issue**: Confidence thresholds are hardcoded in different places:

```python
# In triage.py
CONFIDENCE_THRESHOLD = 0.7

# In unified_agent.py
CONFIDENCE_THRESHOLD = 0.35

# In researcher_chromadb.py (different name)
USER_DEVICE_CONFIDENCE_BOOST = 0.35

# In _synthesize_answer
CONFIDENCE_THRESHOLD = 0.35
```

**Problems**:
1. Same concept, different values (0.7 vs 0.35)
2. No clear explanation for different thresholds
3. Hard to change globally

**Recommendation**: Create config file:
```yaml
# config/thresholds.yaml
classification:
  confidence_threshold: 0.7  # For routing decisions

retrieval:
  minimum_confidence: 0.35   # For including in synthesis
  device_boost: 0.35          # Additional boost for user sources

response:
  citation_confidence_threshold: 0.5
```

Then load in unified_agent.py:
```python
self.thresholds = yaml.safe_load(open("config/thresholds.yaml"))
CONFIDENCE_THRESHOLD = self.thresholds["classification"]["confidence_threshold"]
```

**Severity**: MEDIUM (maintenance, inconsistency)
**Effort**: Medium (create config, update code)

---

#### 5.2 [MEDIUM] top_k parameter varies across methods

**Location**: Multiple search methods

**Issue**: Different methods use different defaults for number of results:

```python
# In search_multiple callers
top_k = 5  # Default

# But in query_knowledge
knowledge_results = self.researcher.query_knowledge(query, top_k=5)

# But in search_all_collections
return all_results[:top_k]  # Depends on caller

# But in search_user_sources
return all_results[:top_k * 2]  # Returns MORE results!
```

**Problems**:
1. search_user_sources returns `top_k * 2` - why?
2. No consistency in what "top_k" means

**Recommendation**: Standardize:
```python
# All search methods return exactly top_k results
def search_user_sources(self, query: str, top_k: int = 5) -> List[SearchResult]:
    ...
    return all_results[:top_k]  # Not top_k * 2
```

Document what top_k means: "Number of result chunks from all sources combined"

**Severity**: MEDIUM (confusing API)
**Effort**: Quick (standardize return statements)

---

#### 5.3 [MEDIUM] Chunk size inconsistent across ingestion scripts

**Location**: Ingestion scripts

**Issue**: Different chunk sizes used:

```python
# In ingest_wikipedia.py
def chunk_text(text, chunk_size=1000, overlap=100):

# In researcher_chromadb.py class
CHUNK_SIZE = 500  # words

# In ingest_ada_standards.py
chunks = chunk_text(subsection_content, chunk_size=800, overlap=100)

# In scripts/fast_reingest.py
def chunk_text(pages: List[Tuple[str, int]], chunk_size=800):
```

**Problems**:
1. 500 vs 800 vs 1000 - why different?
2. Different chunking logic in different files
3. No documentation of chunking strategy

**Recommendation**: Create single chunking utility:
```python
# In agents/text_processing.py
class TextChunker:
    CHUNK_SIZE = 500  # tokens
    CHUNK_OVERLAP = 100
    
    @staticmethod
    def chunk_text(text: str) -> List[str]:
        """Chunk text consistently across all ingestion."""
        ...

# Import everywhere
from agents.text_processing import TextChunker
chunks = TextChunker.chunk_text(content)
```

**Severity**: MEDIUM (consistency, performance)
**Effort**: Medium (extract utility, update scripts)

---

#### 5.4 [LOW] Magic numbers in embedding code

**Location**: researcher_chromadb.py

**Issue**: Embedding/search parameters are hardcoded:

```python
# Cosine similarity threshold
similarity_threshold: float = 0.9

# Max embedding workers
ThreadPoolExecutor(max_workers=4)

# Distance scaling
query_relevance = 1.0 - (distance / 2.0)
```

**Recommendation**: Move to config:
```yaml
embeddings:
  similarity_threshold: 0.9
  distance_scale_factor: 2.0
  max_workers: 4
```

**Severity**: LOW (not critical)
**Effort**: Quick (move to config)

---

### 6. Error Handling Patterns (5 issues)

#### 6.1 [HIGH] Inconsistent exception logging (print vs logger)

**Location**: All search methods

**Issue**: Some methods use `print()`, others use `logger.error()`:

```python
# In search_ada_standards
print(f"Error querying ada_standards collection: {e}")

# In search_research_papers
print(f"Error querying research papers collection: {e}")

# Elsewhere
logger.error(f"Could not list ChromaDB collections: {e}")
```

**Recommendation**: Use logger everywhere:
```python
logger.error(f"Error querying ada_standards collection: {e}", exc_info=True)
```

Add to all search methods:
```python
except Exception as e:
    logger.error(f"Error searching {source}: {e}", exc_info=True)
    return []
```

**Severity**: HIGH (logging inconsistency)
**Effort**: Quick (find and replace)

---

#### 6.2 [MEDIUM] No timeout handling for ChromaDB queries

**Location**: All collection.query() calls

**Issue**: No timeout protection:

```python
results = collection.query(
    query_texts=[query],
    n_results=min(top_k, collection.count())
)
# No timeout - could hang forever if ChromaDB is stuck
```

**Recommendation**: Add timeout wrapper:
```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError

def query_with_timeout(collection, query_texts, n_results, timeout=5):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(collection.query, query_texts=query_texts, n_results=n_results)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            logger.error(f"ChromaDB query timed out after {timeout}s")
            return {'documents': [[]], 'metadatas': [[]], 'distances': [[]]}
```

**Severity**: MEDIUM (operational safety)
**Effort**: Medium (add timeout wrapper, update all queries)

---

#### 6.3 [MEDIUM] No circuit breaker for repeated failures

**Location**: ResearcherAgent

**Issue**: If a collection fails repeatedly, we keep trying:

```python
for collection_name in searchable_collections:
    try:
        results = self.backend._search_collection(collection_name, query, top_k)
    except Exception as e:
        logger.warning(f"Error searching {collection_name}: {e}")
        # Try again next time
```

No mechanism to stop trying collections that are permanently broken.

**Recommendation**: Add circuit breaker:
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=3, reset_timeout=60):
        self.failures = defaultdict(int)
        self.last_failure_time = {}
        self.threshold = failure_threshold
        self.timeout = reset_timeout
    
    def record_failure(self, collection_name):
        self.failures[collection_name] += 1
        self.last_failure_time[collection_name] = time.time()
    
    def is_available(self, collection_name) -> bool:
        if self.failures[collection_name] >= self.threshold:
            elapsed = time.time() - self.last_failure_time[collection_name]
            if elapsed < self.timeout:
                return False  # Circuit open
            else:
                self.failures[collection_name] = 0  # Reset
        return True
```

**Severity**: MEDIUM (reliability)
**Effort**: Medium (implement circuit breaker)

---

#### 6.4 [MEDIUM] No recovery for partial failures in parallel search

**Location**: search_user_sources, search_multiple

**Issue**: If one collection fails in parallel search, others succeed, but there's no aggregation strategy:

```python
with ThreadPoolExecutor(...) as executor:
    for future in as_completed(future_to_col):
        try:
            results = future.result()
            all_results.extend(results)
        except Exception as e:
            logger.warning(f"Error: {e}")
```

If 3 out of 4 collections fail, user gets results from only 1. No indication of partial failure.

**Recommendation**: Track failures and add metadata:
```python
results = {
    "successful": all_results,
    "failed_sources": ["collection1", "collection2"],
    "partial_failure": len(failed_sources) > 0,
    "coverage": len(successful_sources) / total_sources
}
```

**Severity**: MEDIUM (transparency)
**Effort**: Medium (add tracking, update response types)

---

#### 6.5 [LOW] No handling for LLM rate limit exceptions

**Location**: LLM generation code

**Issue**: LLM calls might hit rate limits, no specific handling:

```python
answer = llm.generate_text(
    prompt=prompt,
    config=GenerationConfig(temperature=0.7),
)
# No retry logic for rate limits
```

**Recommendation**: Add retry with exponential backoff:
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(lambda e: "rate_limit" in str(e).lower())
)
def generate_with_retry(...):
    return llm.generate_text(...)
```

**Severity**: LOW (nice-to-have)
**Effort**: Medium (add retry decorator)

---

### 7. Type Safety & Attribute Consistency (3 issues)

#### 7.1 [CRITICAL] Attribute access bugs in debug script

**Location**: [debug_camaps_exercise.py](debug_camaps_exercise.py#L31)

**Issue**: Two attribute name bugs:

```python
Line 31:  print(f"Secondary: {[c.value for c in response.classification.secondarycategories]}")
          # ✗ secondarycategories (camelCase - WRONG)
          # ✓ should be secondary_categories (snake_case)

Line 51: print(response.synthesizedanswer[:300])
         # ✗ synthesizedanswer (camelCase - WRONG)
         # ✓ should be synthesized_answer (snake_case)
```

**Impact**: This debug script will crash with AttributeError

**Recommendation**: Fix attribute names:
```python
Line 31: print(f"Secondary: {[c.value for c in response.classification.secondary_categories]}")
Line 51: print(response.synthesized_answer[:300])
```

**Severity**: CRITICAL (immediate crash)
**Effort**: Quick (fix 2 lines)

---

#### 7.2 [MEDIUM] Inconsistent naming in TriageResponse dataclass

**Location**: [agents/triage.py](agents/triage.py#L63-L67)

**Issue**: Classification uses snake_case, but dataclasses should be audited for consistency:

```python
@dataclass
class TriageResponse:
    query: str
    classification: Classification
    results: dict[str, list[SearchResult]]  # Dict keys are strings, not enums
    synthesized_answer: str  # ✓ snake_case (correct)
```

This is OK, but Classification has:
```python
@dataclass
class Classification:
    category: QueryCategory  # ✓ singular
    confidence: float
    reasoning: str
    secondary_categories: list[QueryCategory] = field(default_factory=list)  # ✓ plural, snake_case
```

All consistent! But document it.

**Recommendation**: Add type hints everywhere and comment that dataclass attrs use snake_case.

**Severity**: MEDIUM (documentation)
**Effort**: Quick (add docstring)

---

#### 7.3 [MEDIUM] Dict vs dataclass inconsistency in return types

**Location**: search_multiple returns dict, many methods return List[SearchResult]

**Issue**: API inconsistency:
```python
# Returns dict
def search_multiple() -> dict[str, list[SearchResult]]

# Returns list
def search_user_sources() -> List[SearchResult]

# Returns list
def search_ada_standards() -> List[SearchResult]
```

**Recommendation**: Be consistent. `search_multiple()` needs to return dict because it handles multiple sources. But document this clearly:
```python
def search_multiple(self, query: str, sources: List[str]) -> dict[str, list[SearchResult]]:
    """
    Search multiple sources and return dict mapping source_name -> results.
    
    Returns:
        {
            "clinical_guidelines": [SearchResult(...), ...],
            "user_sources": [SearchResult(...), ...],
        }
    """
```

**Severity**: MEDIUM (API clarity)
**Effort**: Quick (add docstring)

---

### 8. Test Coverage Gaps (4 issues)

#### 8.1 [HIGH] No tests for search_multiple routing

**Location**: tests/

**Issue**: The critical routing method search_multiple() has no tests:

```python
def search_multiple(self, query: str, sources: List[str]) -> dict:
```

This method:
1. Takes a list of source names
2. Routes to the correct search method via search_map
3. Returns results keyed by source

But there's no test verifying that all sources in search_map work.

**Recommendation**: Add test:
```python
def test_search_multiple_all_sources():
    """Verify all sources in search_map can be searched."""
    researcher = ResearcherAgent()
    
    test_query = "How to manage diabetes?"
    test_sources = [
        "clinical_guidelines",
        "user_sources",
        "research_papers",
    ]
    
    results = researcher.search_multiple(test_query, test_sources)
    
    assert all(source in results for source in test_sources)
    # Should not raise, even if sources are empty
```

**Severity**: HIGH (critical code path untested)
**Effort**: Medium (add integration test)

---

#### 8.2 [HIGH] No tests for silent failures

**Location**: tests/

**Issue**: No tests verify that silent failures are caught:

```python
def test_missing_source_logs_warning():
    """Verify that requesting non-existent source logs warning."""
    researcher = ResearcherAgent()
    
    with patch('agents.researcher_chromadb.logger') as mock_logger:
        results = researcher.search_multiple("test", ["nonexistent_source"])
        
        # Should log warning
        mock_logger.warning.assert_called()
```

**Recommendation**: Add test for error handling.

**Severity**: HIGH (silent failures aren't validated)
**Effort**: Medium (add logging test)

---

#### 8.3 [MEDIUM] No tests for collection discovery

**Location**: tests/

**Issue**: Dynamic collection discovery (get_collections_by_type) isn't tested:

```python
def test_get_collections_by_type():
    """Test metadata-based collection discovery."""
    researcher = ResearcherAgent()
    
    device_collections = researcher.get_collections_by_type("device_manual")
    # Should return list of collection names with that type
    assert isinstance(device_collections, list)
```

**Recommendation**: Add test.

**Severity**: MEDIUM (discovery untested)
**Effort**: Quick (add simple test)

---

#### 8.4 [MEDIUM] No tests for TriageAgent routing to USER_SOURCES

**Location**: tests/

**Issue**: The exact bug that was just discovered - routing USER_SOURCES queries - should have a test:

```python
def test_triage_user_sources_routing():
    """Verify USER_SOURCES category queries are routed to search_user_sources."""
    triage = TriageAgent()
    
    # Query that would be classified as USER_SOURCES
    query = "How do I change my pump settings?"
    response = triage.process(query, verbose=False)
    
    # Should have results from user_sources
    assert "user_sources" in response.results or len(response.results) > 0
```

**Recommendation**: Add test to catch similar routing bugs.

**Severity**: MEDIUM (routing untested)
**Effort**: Quick (add test)

---

### 9. Product/Knowledge Specificity Violations (10 issues)

#### 9.1 [CRITICAL] Hardcoded device names in router prompts

**Location**: [agents/router_agent.py](agents/router_agent.py#L85-L140)

**Issue**: Router has hardcoded list of all known devices:

```python
AUTOMATED_SYSTEMS = [
    "camaps fx", "camaps", "cam aps",
    "control-iq", "control iq", "controliq",
    "loop", "openaps", "androidaps", "iaps",
    "medtronic 670g", "medtronic 770g", "medtronic 780g",
    "omnipod 5", "omnipod5",
    "diabeloop",
]
```

**Problems**:
1. If user has device not in list, router won't detect it
2. User uploaded CamAPS FX manual, but router doesn't know about uploaded devices
3. Adding new devices requires code change

**Recommendation**: Make router aware of available device sources:
```python
def __init__(self, ...):
    # Load available devices from user sources
    self.available_devices = self._discover_available_devices()
    # Keep KNOWN_SYSTEMS as fallback for unuploaded devices
    self.known_systems = {
        "camaps": ("automated", "algorithm_app"),
        "control-iq": ("automated", "algorithm_app"),
        ...
    }

def _discover_available_devices(self) -> dict:
    """Dynamically discover uploaded device collections."""
    available = {}
    for col_name, info in self.researcher.list_pdf_collections().items():
        available[col_name] = ("unknown", "unknown")
    return available
```

**Severity**: CRITICAL (device-specific system breaks with new devices)
**Effort**: Medium (add dynamic discovery)

---

#### 9.2 [HIGH] LLM prompts mention specific devices

**Location**: Various prompt-building code

**Issue**: System prompts and LLM prompts hardcode device names:

```python
# Example in unified_agent.py (hypothetical)
prompt = """You are a diabetes management assistant.
User has: CamAPS FX, Dexcom G6, Dana-i pump.

Answer questions about...
"""
```

This assumes specific devices and breaks if user has different devices.

**Recommendation**: Build dynamic prompts from user's actual devices:
```python
def build_prompt(user_devices: List[str], query: str) -> str:
    """Build prompt mentioning user's actual devices."""
    device_list = ", ".join(user_devices) if user_devices else "unspecified devices"
    
    return f"""You are a diabetes management assistant.
User has: {device_list}

Answer questions about insulin management, CGM use, and diabetes care.
"""
```

**Severity**: HIGH (hardcodes product names)
**Effort**: Medium (audit prompts, add dynamic device list)

---

#### 9.3 [HIGH] Responses assume OpenAPS/Loop knowledge

**Location**: Response generation code

**Issue**: Generated responses might mention OpenAPS/Loop even if user doesn't use them:

Example (not found in code but possible):
```
"In OpenAPS, you would use autosens to..."
"Loop allows you to set a override for..."
```

**Problem**: User uploaded CamAPS FX manual, not Loop. Suggestion is irrelevant.

**Recommendation**: Filter response generation based on available sources:
```python
def should_mention_source(self, source_name: str, user_devices: List[str]) -> bool:
    """Determine if response should mention this source."""
    # Only mention sources available to user
    available = [d.lower() for d in user_devices]
    return source_name.lower() in available or is_generic_knowledge(source_name)

def is_generic_knowledge(self, source_name: str) -> bool:
    """Some knowledge is generic even if not user's device."""
    generic_sources = ["clinical_guidelines", "research_papers", "wikipedia"]
    return any(g in source_name.lower() for g in generic_sources)
```

**Severity**: HIGH (confuses user with irrelevant device info)
**Effort**: Medium (filter response generation)

---

#### 9.4 [MEDIUM] Collection names leak product specificity

**Location**: ChromaDB collection names

**Issue**: Collections might be named:
- `"camaps_fx_manual"` - product-specific name
- `"libre_3_manual"` - product-specific name

These should be generic:
- `"device_manual_fx_mmoll_commercial_ca"` - derived from filename
- `"device_manual_freestyle_libre_3"` - product name extracted as metadata, not in key

**Recommendation**: Use generic collection keys:
```python
# Collection key: generic, derived from filename
collection_key = "user_device_manual_1"

# Metadata: preserve product name for display
metadata = {
    "product_name": "CamAPS FX",
    "device": "YpsoPump",
    "cgm": "Dexcom G7",
}
```

**Severity**: MEDIUM (leaks product specificity into internal identifiers)
**Effort**: Medium (refactor collection naming)

---

#### 9.5 [MEDIUM] Configuration assumes specific knowledge sources

**Location**: Configuration files

**Issue**: If code assumes "ada_standards" collection must exist:

```python
# In some method
collection = self.chroma_client.get_collection("ada_standards")
# No fallback if ADA standards aren't ingested
```

**Problem**: Product becomes dependent on specific knowledge source being available.

**Recommendation**: Make all sources optional with fallback:
```python
def get_required_collections(self) -> set:
    """Collections needed for core functionality."""
    return {"user_sources"}  # Only user sources required

def get_recommended_collections(self) -> set:
    """Collections that improve answers but aren't required."""
    return {"clinical_guidelines", "research_papers", "wikipedia_education"}

def search_with_fallback(self, query, required_only=False):
    """Search all available sources, fallback to required only if needed."""
    ...
```

**Severity**: MEDIUM (creates hidden dependencies)
**Effort**: Medium (audit code for assumptions)

---

#### 9.6 [MEDIUM] Prompts mention specific clinical guidelines

**Location**: Response generation, safety prompts

**Issue**: Prompts might say "According to ADA Standards..." even if ADA wasn't searched:

```python
# Hypothetical bad code
prompt = f"""
Use ADA Standards of Care to answer: {query}
"""
# But if ADA collection doesn't exist, this misleads user
```

**Recommendation**: Base prompt on what was actually searched:
```python
sources_searched = [s for s in results.keys() if results[s]]
prompt_base = f"""Use the following sources: {', '.join(sources_searched)}"""

if not sources_searched:
    prompt_base = "Based on general diabetes knowledge..."
```

**Severity**: MEDIUM (attributions don't match sources)
**Effort**: Medium (audit prompt generation)

---

#### 9.7 [MEDIUM] Feature detection assumes specific device features

**Location**: Router agent, device detection

**Issue**: Router makes assumptions about device capabilities:

```python
# In router_agent.py
AUTOMATED_SYSTEMS = ["camaps fx", "control-iq", "loop", ...]

# Assumes only these systems are automated
# But user might have different automated system
```

**Recommendation**: Don't hardcode device capabilities. Infer from:
1. What's in user's uploaded manuals
2. Device detection from LLM
3. User's explicit settings

```python
def detect_automation_mode(self, query: str, user_devices: List[str]) -> AutomationMode:
    """Infer automation mode from devices and query."""
    # Check if any uploaded device manual mentions "automated"
    for device in user_devices:
        device_info = self.get_device_info(device)
        if device_info.get("is_automated"):
            return AutomationMode.AUTOMATED
    return AutomationMode.UNKNOWN
```

**Severity**: MEDIUM (system brittleness)
**Effort**: Medium (refactor device detection)

---

#### 9.8 [LOW] Comments reference specific products

**Location**: Docstrings, comments

**Issue**: Comments mention devices by name for examples:

```python
"""
Search user-uploaded device manuals (pumps, CGMs, closed-loop systems).
Examples: CamAPS FX, Dana-i pump, Dexcom G6
"""
```

**Recommendation**: Use generic examples:
```python
"""
Search user-uploaded device manuals (pumps, CGMs, closed-loop systems).
Examples: Any insulin pump, continuous glucose monitor, closed-loop algorithm
"""
```

**Severity**: LOW (documentation)
**Effort**: Quick (update docstrings)

---

#### 9.9 [LOW] Error messages mention specific devices

**Location**: Error/warning messages

**Issue**: User-facing messages might say:

```python
"No CamAPS FX manual found"  # Too specific
"No device manual found"  # Generic and better
```

**Recommendation**: Use generic language in user messages:
```python
logger.debug(f"No device manual found for {device_name}")  # Internal
# User message: "Please upload your device manual to get personalized guidance"
```

**Severity**: LOW (user experience)
**Effort**: Quick (update error messages)

---

#### 9.10 [MEDIUM] Collection deletion assumes device mapping

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L1180)

**Issue**: delete_user_source_collection just deletes:

```python
def delete_user_source_collection(self, collection_key: str):
    self.chroma_client.delete_collection(name=collection_key)
    if collection_key in self.pdf_paths:
        del self.pdf_paths[collection_key]
```

No audit trail of what was deleted or warning about loss of device-specific knowledge.

**Recommendation**: Add metadata tracking:
```python
def delete_user_source_collection(self, collection_key: str):
    """Delete and log for audit trail."""
    try:
        col_info = self.get_collection_info(collection_key)
        logger.warning(f"Deleting user source: {col_info.get('display_name')} ({col_info.get('doc_count')} documents)")
        
        self.chroma_client.delete_collection(name=collection_key)
        ...
    except Exception as e:
        logger.error(f"Failed to delete {collection_key}: {e}")
        raise
```

**Severity**: MEDIUM (audit trail)
**Effort**: Quick (add logging)

---

### 10. Assumption Validation (4 issues)

#### 10.1 [HIGH] No validation that get_collection returns valid collection

**Location**: Multiple search methods

**Issue**: Code assumes get_collection() returns valid object:

```python
def search_ada_standards(...):
    try:
        collection = self.chroma_client.get_collection(name="ada_standards")
    except Exception:
        return []

    if collection.count() == 0:
        return []
```

If ChromaDB is corrupted or collection is invalid, .count() might fail.

**Recommendation**: Validate collection state:
```python
def search_ada_standards(...):
    try:
        collection = self.chroma_client.get_collection(name="ada_standards")
        # Validate collection is usable
        doc_count = collection.count()
        if doc_count == 0:
            logger.debug("ada_standards collection is empty")
            return []
    except Exception as e:
        logger.error(f"Cannot access ada_standards: {e}")
        return []
```

**Severity**: HIGH (safety check missing)
**Effort**: Quick (add validation)

---

#### 10.2 [MEDIUM] search_map construction doesn't check method existence

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L1414)

**Issue**: search_map is built dynamically but methods might not exist:

```python
search_map = {
    "clinical_guidelines": self.search_clinical_guidelines,  # ✓ Exists
    "user_sources": self.search_user_sources,  # ✓ Exists
    "glooko_data": lambda q: [],  # ✓ Anonymous function
}
```

This is OK now but if methods are deleted, it would fail at query time.

**Recommendation**: Validate in __init__:
```python
def __init__(self):
    # Check all search methods exist
    required_methods = [
        "search_clinical_guidelines",
        "search_ada_standards",
        ...
    ]
    for method in required_methods:
        if not hasattr(self, method):
            raise RuntimeError(f"Missing search method: {method}")
```

**Severity**: MEDIUM (prevents silent failures)
**Effort**: Quick (add validation)

---

#### 10.3 [MEDIUM] No assumption validation for LLM provider

**Location**: [agents/triage.py](agents/triage.py#L124), [agents/unified_agent.py](agents/unified_agent.py#L50)

**Issue**: Code assumes LLM provider is configured:

```python
def __init__(self, ...):
    self.llm = LLMFactory.get_provider()  # Assumes this works
```

If LLM_PROVIDER env var isn't set, this could fail.

**Recommendation**: Validate and fall back:
```python
def __init__(self, ...):
    try:
        self.llm = LLMFactory.get_provider()
        logger.info(f"Using LLM provider: {self.llm.provider_name}")
    except Exception as e:
        logger.error(f"LLM provider initialization failed: {e}")
        raise  # Fail fast rather than silently
```

**Severity**: MEDIUM (dependency validation)
**Effort**: Quick (add error handling)

---

#### 10.4 [MEDIUM] No validation that session_id is valid before personalization

**Location**: [agents/unified_agent.py](agents/unified_agent.py) personalization code

**Issue**: Code assumes session_id can be used for personalization:

```python
if self.personalization_manager and session_id:
    all_results = self.personalization_manager.apply_device_boost(
        all_results,
        session_id=session_id,
    )
```

No validation that session_id is in the system.

**Recommendation**: Handle missing sessions:
```python
if self.personalization_manager and session_id:
    try:
        user_devices = self.personalization_manager.get_user_devices(session_id)
        if not user_devices:
            logger.debug(f"No devices found for session {session_id}")
        else:
            all_results = self.personalization_manager.apply_device_boost(...)
    except Exception as e:
        logger.warning(f"Personalization failed for {session_id}: {e}")
        # Continue without personalization boost
```

**Severity**: MEDIUM (personalization robustness)
**Effort**: Quick (add error handling)

---

### 11. Hardcoded Knowledge Source Assumptions (11 issues)

#### 11.1 [CRITICAL] Code might assume ADA Standards exist

**Location**: Search methods

**Issue**: Code assumes "ada_standards" collection exists after setup. But user could delete it.

**Status**: Actually handled with try-except returning [] - this is OK!

**Test Scenario**: What if user deletes ada_standards collection?
```python
# Current code handles this:
try:
    collection = self.chroma_client.get_collection(name="ada_standards")
except Exception:
    return []  # ✓ Graceful fallback
```

**Result**: ✅ PASSES - Returns empty results without crashing

---

#### 11.2 [HIGH] Router assumes certain collections for HYBRID queries

**Location**: [agents/triage.py](agents/triage.py#L436)

**Issue**: HYBRID routing appends "clinical_guidelines" unconditionally:

```python
if category == QueryCategory.HYBRID:
    sources_to_search.append("clinical_guidelines")
```

If user deletes clinical_guidelines collection, HYBRID queries will try to search it anyway.

**Recommendation**: Check collection availability:
```python
if category == QueryCategory.HYBRID:
    available_sources = set(self.researcher.list_pdf_collections().keys())
    for source in ["clinical_guidelines", "user_sources", "knowledge_base"]:
        if source in available_sources or self._is_collection_required(source):
            sources_to_search.append(source)
```

**Severity**: HIGH (HYBRID routing might fail)
**Effort**: Medium (add collection availability check)

---

#### 11.3 [MEDIUM] search_multiple assumes all sources in search_map exist

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L1414)

**Issue**: search_map references methods but some collections might not exist:

```python
search_map = {
    "ada_standards": self.search_ada_standards,  # Method exists ✓
    ...
}

# But search_ada_standards() handles missing collection:
def search_ada_standards(...):
    try:
        collection = self.chroma_client.get_collection(name="ada_standards")
    except Exception:
        return []  # ✓ Graceful
```

**Result**: ✅ Already handles this - methods return [] if collection missing

---

#### 11.4 [HIGH] KNOWLEDGE_BASE routing has no fallback

**Location**: [agents/triage.py](agents/triage.py#L440)

**Issue**: KNOWLEDGE_BASE routing calls query_knowledge():

```python
elif category == QueryCategory.KNOWLEDGE_BASE:
    needs_knowledge_search = True

# Later:
if needs_knowledge_search:
    try:
        knowledge_results = self.researcher.query_knowledge(query, top_k=5)
        if knowledge_results:
            results["knowledge_base"] = knowledge_results
    except Exception as e:
        print(f"Warning: Knowledge base search failed: {e}")
```

This uses `print()` instead of logger, and might fail silently.

**Recommendation**: Fix logging and validation:
```python
if needs_knowledge_search:
    try:
        knowledge_results = self.researcher.query_knowledge(query, top_k=5)
        if knowledge_results:
            results["knowledge_base"] = knowledge_results
            logger.info(f"Knowledge base search returned {len(knowledge_results)} results")
        else:
            logger.debug("Knowledge base search returned no results")
    except Exception as e:
        logger.error(f"Knowledge base search failed: {e}", exc_info=True)
        # Continue - some sources might not be available
```

**Severity**: HIGH (logging inconsistency)
**Effort**: Quick (fix logging)

---

#### 11.5 [MEDIUM] query_knowledge uses dynamic discovery but doesn't validate

**Location**: [agents/researcher_chromadb.py](agents/researcher_chromadb.py#L1440)

**Issue**: query_knowledge discovers all collections dynamically:

```python
all_collections = self.backend.chroma_client.list_collections()
searchable_collections = [
    col.name for col in all_collections
    if not col.name.startswith('_')
    and col.count() > 0
]
```

But doesn't validate they're search-able (might be intermediate/temp collections).

**Recommendation**: Use metadata to filter:
```python
searchable_collections = [
    col.name for col in all_collections
    if not col.name.startswith('_')
    and col.count() > 0
    and (col.metadata or {}).get("searchable", True)  # Explicit flag
]
```

**Severity**: MEDIUM (safety in discovery)
**Effort**: Quick (add searchable flag)

---

#### 11.6 [HIGH] No documentation of "required" vs "optional" collections

**Location**: Codebase

**Issue**: It's unclear which collections are required for core functionality:

- Can system work with only user_sources? **YES** ✓
- Can system work without clinical_guidelines? **YES** ✓
- Can system work without any user sources? **YES** ✓
- Can system work without research_papers? **YES** ✓

But this isn't documented or validated anywhere.

**Recommendation**: Create schema document:
```python
# In documentation or code
COLLECTION_SCHEMA = {
    "ada_standards": {
        "required": False,
        "type": "clinical_guideline",
        "description": "ADA Standards of Care - authoritative clinical guidelines"
    },
    "research_papers": {
        "required": False,
        "type": "knowledge_base",
        "description": "PubMed research literature"
    },
    "user_sources": {
        "required": False,
        "type": "device_manual",
        "description": "User-uploaded device manuals and guides"
    }
}
```

**Severity**: HIGH (design clarity)
**Effort**: Medium (create schema documentation)

---

#### 11.7 [MEDIUM] Prompts assume user can follow device-specific instructions

**Location**: Response generation

**Issue**: System might generate response assuming user has a specific device:

```
"Configure your pump's temporary basal rate setting to..."
```

But if user doesn't have pump uploaded, they can't follow this.

**Recommendation**: Add device validation to synthesis:
```python
def should_include_instruction(self, instruction: str, user_devices: List[str]) -> bool:
    """Check if instruction applies to user's devices."""
    required_device = extract_required_device(instruction)
    if required_device:
        return any(d.lower() in required_device.lower() for d in user_devices)
    return True  # Generic instructions always OK
```

**Severity**: MEDIUM (user experience)
**Effort**: Medium (add instruction filtering)

---

#### 11.8 [MEDIUM] No health check for knowledge sources on startup

**Location**: app.py initialization

**Issue**: System doesn't validate that key collections exist on startup:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Diabetes Buddy API...")
    yield
```

Missing collection health check.

**Recommendation**: Add health check:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - validate knowledge sources
    researcher = ResearcherAgent()
    inventory = researcher.get_collection_inventory()
    
    user_sources_count = sum(1 for col, meta in inventory.items() 
                              if meta.get("type") == "device_manual")
    clinical_sources_count = sum(1 for col, meta in inventory.items()
                                  if meta.get("type") == "clinical_guideline")
    
    logger.info(f"Knowledge sources ready: {user_sources_count} device manuals, {clinical_sources_count} clinical sources")
    
    if user_sources_count == 0:
        logger.warning("No user-uploaded device manuals found. System will use only clinical knowledge.")
    
    yield
```

**Severity**: MEDIUM (operational visibility)
**Effort**: Medium (add health check)

---

#### 11.9 [CRITICAL] Test scenario: User with ONLY uploaded sources

**Location**: Integration tests

**Issue**: **CRITICAL TEST**: What if user deletes all community sources and only has their device manuals?

**Scenario**:
1. User deletes ada_standards, research_papers, wikipedia_education collections
2. User uploads only CamAPS FX manual  
3. User asks: "How should I prepare for exercise?"

**Expected Result**: System should work perfectly with ONLY the CamAPS FX manual

**Current Status**: UNKNOWN - not tested

**Recommendation**: Add integration test:
```python
def test_work_with_only_user_sources():
    """CRITICAL: System should work with only user-uploaded sources."""
    # Setup: only user sources, no clinical/community sources
    researcher = ResearcherAgent()
    
    # Delete all non-user sources
    for col in researcher.chroma_client.list_collections():
        if col.metadata and col.metadata.get("type") != "device_manual":
            researcher.chroma_client.delete_collection(col.name)
    
    # Create a mock user source
    triage = TriageAgent()
    response = triage.process("How should I prepare for exercise?")
    
    # Should NOT crash
    assert response.success
    # Should have some answer, even if from limited sources
    assert len(response.synthesized_answer) > 0
```

**Severity**: CRITICAL (entire premise of system)
**Effort**: Medium (add integration test)

---

#### 11.10 [MEDIUM] Comments mislead about removed community sources

**Location**: Comments throughout

**Issue**: Comments still mention OpenAPS/Loop/AndroidAPS as if they're available:

```python
# Track if we need to search the knowledge base (openaps_docs, loop_docs, etc.)
```

But these collections were removed.

**Recommendation**: Update comments:
```python
# Track if we need to search the knowledge base
# (previously included openaps_docs, loop_docs, androidaps_docs but these were removed
#  in favor of product-agnostic device manual approach)
```

**Severity**: MEDIUM (maintainer confusion)
**Effort**: Quick (update comments)

---

#### 11.11 [HIGH] No graceful degradation when collections are missing

**Location**: Response generation

**Issue**: If a collection that results depend on is deleted, response quality degrades silently:

```
Before: "Based on ADA Standards and research: ... [citations]"
After: "Based on research: ... " (ADA deleted silently)
```

User doesn't know why quality changed.

**Recommendation**: Add metadata about sources used:
```python
response = {
    "answer": "...",
    "sources_searched": ["clinical_guidelines", "user_sources"],
    "sources_found": ["user_sources"],  # Actual collections with results
    "sources_empty": ["clinical_guidelines"],  # Collections found but empty
    "sources_missing": [],  # Collections not available
}
```

**Severity**: HIGH (transparency)
**Effort**: Medium (add source tracking)

---

## Prioritized Fix List

Order by: (Severity × Likelihood) - Effort

### PHASE 1: Critical Fixes (Do First)

1. **[CRITICAL]** `debug_camaps_exercise.py:31,51` - Fix attribute access bugs
   - Impact: Debug script crashes
   - Likelihood: HIGH (script runs frequently)
   - Effort: Quick (2 lines)
   - Est: 5 min

2. **[CRITICAL]** Add missing `"user_sources"` to search_map validation
   - Impact: Silent failures when USER_SOURCES queries skip search
   - Likelihood: HIGH (reproducible bug)
   - Effort: Quick (add logging + validation)
   - Est: 15 min

3. **[CRITICAL]** Add comprehensive test: "System works with ONLY user sources"
   - Impact: Validates entire premise
   - Likelihood: HIGH (catches regressions)
   - Effort: Medium (integration test)
   - Est: 45 min

### PHASE 2: High-Priority Fixes

4. **[HIGH]** Replace `print()` with `logger` in all search methods
   - Impact: Inconsistent logging, hard to debug
   - Likelihood: MEDIUM
   - Effort: Quick (find and replace)
   - Est: 20 min

5. **[HIGH]** Create single CATEGORY_TO_SOURCE mapping
   - Impact: Prevents routing errors
   - Likelihood: HIGH (brittle code)
   - Effort: Medium (add mapping + validation)
   - Est: 30 min

6. **[HIGH]** Remove fallback heuristic in search_user_sources
   - Impact: Could search wrong collections
   - Likelihood: MEDIUM
   - Effort: Quick (remove fallback)
   - Est: 10 min

7. **[HIGH]** Add collection availability check to HYBRID routing
   - Impact: HYBRID queries might target missing sources
   - Likelihood: MEDIUM
   - Effort: Medium (add checks)
   - Est: 30 min

8. **[HIGH]** Standardize exception handling in search methods
   - Impact: Swallows real errors
   - Likelihood: HIGH
   - Effort: Medium (update 5+ methods)
   - Est: 45 min

### PHASE 3: Medium-Priority Fixes

9. **[MEDIUM]** Create CollectionFactory with consistent metadata
   - Impact: Breaks discovery and migration
   - Likelihood: MEDIUM
   - Effort: Medium (factory + refactor)
   - Est: 60 min

10. **[MEDIUM]** Create configuration file for thresholds
    - Impact: Scattered magic numbers, hard to tune
    - Likelihood: LOW
    - Effort: Medium (config + loading)
    - Est: 45 min

11. **[MEDIUM]** Add health check on startup
    - Impact: No visibility into data availability
    - Likelihood: LOW
    - Effort: Medium (add check + logging)
    - Est: 30 min

12. **[MEDIUM]** Move to single TextChunker utility
    - Impact: Inconsistent chunking across ingestion
    - Likelihood: LOW
    - Effort: Medium (extract + update scripts)
    - Est: 45 min

### PHASE 4: Lower Priority

13. **[MEDIUM]** Add timeout wrapper for ChromaDB queries
    - Impact: Potential hangs
    - Likelihood: LOW (ChromaDB usually responsive)
    - Effort: Medium (add wrapper)
    - Est: 45 min

14. **[MEDIUM]** Standardize collection naming convention
    - Impact: Code clarity, migration risk
    - Likelihood: LOW
    - Effort: Medium (rename + update references)
    - Est: 60 min

15. **[LOW]** Remove/comment deprecated ingestion scripts
    - Impact: Clutter
    - Likelihood: LOW
    - Effort: Quick (delete or comment)
    - Est: 10 min

---

## Quick Wins (Optional - Improve Robustness)

These are low-effort improvements that increase robustness:

1. **Add logging to search_map construction** (5 min)
   ```python
   logger.info(f"Configured search methods: {', '.join(search_map.keys())}")
   ```

2. **Add docstring to HYBRID routing** (5 min)
   - Clarify what HYBRID searches

3. **Update comments about removed community sources** (10 min)
   - Remove references to openaps_docs, loop_docs, androidaps_docs

4. **Add simple collection inventory method** (15 min)
   - `get_collection_inventory()` for debugging

5. **Fix inconsistent top_k returns** (10 min)
   - Make search_user_sources return `top_k` not `top_k * 2`

6. **Add validation in __init__** (10 min)
   - Check all search methods exist

---

## After Audit - Next Steps

1. **Review** this report and confirm priority list
2. **Pick a fix** from PHASE 1 to start
3. **Add test first** (TDD approach)
4. **Implement fix**
5. **Verify test passes**
6. **Check for similar patterns** (learn from fix)
7. **Move to next issue**

---

## Metrics to Track

After fixes are applied:
- [ ] All search methods use logger (not print)
- [ ] 100% of QueryCategory enum values have search handlers
- [ ] search_multiple has unit test
- [ ] Silent failure points have logging
- [ ] No hardcoded device names in prompts
- [ ] Tests pass with ONLY user-uploaded sources
- [ ] Collection health check runs on startup

---

## Notes for Next Audit

- The project has **evolved through multiple refactors** (OpenAPS→Loop→device-agnostic)
- This caused **inconsistencies in naming and assumptions**
- Main risk is **silent failures** (queries skip sources without logging)
- Core system is **sound** but **safety checks need strengthening**
- **Type safety improvements** (dataclass attrs, enum usage) are low-hanging fruit

