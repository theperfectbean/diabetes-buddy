# Device-Aware Knowledge Prioritization - Implementation Plan

**Created:** February 3, 2026
**Status:** Ready for Implementation
**Objective:** Prioritize user-uploaded device documentation and remove conflicting community system advice

---

## Overview

This plan transforms Diabetes Buddy from generic diabetes advice to **device-specific guidance** tailored to each user's actual equipment. User-uploaded device manuals become the PRIMARY knowledge source, while conflicting community documentation (OpenAPS/Loop/AndroidAPS) is removed.

---

## Task 1: Remove Community System Documentation

### Files to Modify
- `agents/researcher_chromadb.py` - Remove collection references
- `scripts/` directory - Delete ingestion scripts

### Files to Delete
```bash
# Check for and delete these if they exist:
scripts/ingest_openaps_docs.py
scripts/ingest_loop_docs.py
scripts/ingest_androidaps_docs.py
```

### ChromaDB Collections to Delete
```python
# Collections to remove programmatically or via script:
- "openaps_docs" or "openapsdocs"
- "loop_docs" or "loopdocs"
- "androidaps_docs" or "androidapsdocs"
```

### Implementation Steps
1. Search codebase for references to these collection names
2. Remove from any `PDF_PATHS`, `COLLECTION_REGISTRY`, or similar configs
3. Delete the ingestion scripts
4. Create a cleanup script to delete ChromaDB collections:

```python
# scripts/cleanup_community_collections.py
import chromadb

def cleanup_community_collections():
    client = chromadb.PersistentClient(path="./chromadb_data")
    collections_to_remove = [
        "openaps_docs", "openapsdocs",
        "loop_docs", "loopdocs",
        "androidaps_docs", "androidapsdocs"
    ]
    for name in collections_to_remove:
        try:
            client.delete_collection(name)
            print(f"Deleted: {name}")
        except Exception as e:
            print(f"Skipped {name}: {e}")

if __name__ == "__main__":
    cleanup_community_collections()
```

### Validation
- Grep codebase for "openaps", "loop_docs", "androidaps" - should return no active references
- List ChromaDB collections - community collections should be gone

---

## Task 2: Apply Confidence Boost to User Device Docs

### File to Modify
`agents/researcher_chromadb.py`

### Location
`search_collection()` method (or equivalent search method)

### Implementation

Find the search method and add boost logic:

```python
# Add constant at top of file
USER_DEVICE_CONFIDENCE_BOOST = 0.35

def search_collection(self, collection_name: str, query: str, n_results: int = 5):
    # ... existing search logic ...

    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )

    # Apply confidence boost for user device collections
    processed_results = []
    for i, (doc, distance) in enumerate(zip(results['documents'][0], results['distances'][0])):
        # Convert distance to confidence (typically 1 - normalized_distance)
        confidence = 1 - (distance / 2)  # Adjust based on actual distance metric

        # Boost user device collections
        if collection_name.startswith("user-") or collection_name.startswith("user_"):
            confidence = min(1.0, confidence + USER_DEVICE_CONFIDENCE_BOOST)
            is_user_device = True
        else:
            is_user_device = False

        processed_results.append({
            "content": doc,
            "confidence": confidence,
            "collection": collection_name,
            "is_user_device": is_user_device,
            "metadata": results['metadatas'][0][i] if results['metadatas'] else {}
        })

    return processed_results
```

### Validation
- Test query returns user device chunks with 0.95+ confidence
- User docs should rank above clinical guidelines (0.8-0.9)

---

## Task 3: Track User's Registered Devices

### File to Modify
`agents/source_manager.py`

### New Method to Add

```python
def get_user_devices(self) -> List[Dict[str, str]]:
    """
    Detect user-uploaded device documentation.

    Returns:
        List of dicts with keys:
        - name: Human-readable device name (e.g., "CamAPS FX User Manual")
        - type: "algorithm" | "pump" | "cgm" | "unknown"
        - collection: ChromaDB collection name (e.g., "user-camaps-fx")
    """
    user_devices = []

    # Method 1: Scan docs/user-sources/ directory
    user_sources_dir = Path("docs/user-sources")
    if user_sources_dir.exists():
        for path in user_sources_dir.glob("**/*.pdf"):
            device_name = path.stem.replace("_", " ").replace("-", " ").title()
            collection_name = f"user-{path.stem.lower().replace(' ', '-')}"
            device_type = self._detect_device_type(device_name)
            user_devices.append({
                "name": device_name,
                "type": device_type,
                "collection": collection_name
            })

    # Method 2: Query ChromaDB for user-* collections
    try:
        client = chromadb.PersistentClient(path="./chromadb_data")
        collections = client.list_collections()
        for coll in collections:
            if coll.name.startswith("user-") or coll.name.startswith("user_"):
                # Extract device name from collection metadata or name
                device_name = coll.name.replace("user-", "").replace("user_", "")
                device_name = device_name.replace("-", " ").replace("_", " ").title()
                if not any(d["collection"] == coll.name for d in user_devices):
                    user_devices.append({
                        "name": device_name,
                        "type": self._detect_device_type(device_name),
                        "collection": coll.name
                    })
    except Exception as e:
        logger.warning(f"Could not query ChromaDB for user collections: {e}")

    return user_devices

def _detect_device_type(self, name: str) -> str:
    """Classify device type based on name keywords."""
    name_lower = name.lower()

    # Algorithm/closed-loop systems
    if any(kw in name_lower for kw in ["camaps", "omnipod 5", "control-iq", "medtronic 780g", "ilet"]):
        return "algorithm"

    # Pumps
    if any(kw in name_lower for kw in ["pump", "omnipod", "tandem", "medtronic", "ypsopump"]):
        return "pump"

    # CGMs
    if any(kw in name_lower for kw in ["dexcom", "libre", "guardian", "cgm", "sensor"]):
        return "cgm"

    return "unknown"
```

### Validation
- Upload a test PDF to `docs/user-sources/`
- Call `get_user_devices()` - should return the device info

---

## Task 4: Device-Aware Synthesis Prompt

### File to Modify
`agents/unified_agent.py`

### Location
`build_prompt()` method

### Current Signature (expected)
```python
def build_prompt(self, query: str, context: str) -> str:
```

### New Signature
```python
def build_prompt(self, query: str, context: str, user_devices: List[str] = None) -> str:
```

### Implementation

```python
def build_prompt(self, query: str, context: str, user_devices: List[str] = None) -> str:
    """Build synthesis prompt with device-aware framing."""

    # Device-specific preamble
    if user_devices and len(user_devices) > 0:
        device_list = ", ".join(user_devices)
        device_preamble = f"""
IMPORTANT CONTEXT: The user is using the following diabetes device(s): {device_list}

Your response MUST be tailored specifically to their system(s). Follow these rules:
1. Prioritize information from the user's device manual above ALL other sources
2. Use personalized language: "your {user_devices[0]}..." NOT "systems like..." or "some pumps..."
3. Reference specific features, menus, and settings from their device
4. If information conflicts between sources, ALWAYS prefer the user's device manual
5. Only mention other devices if directly relevant for comparison the user requested

Knowledge Source Priority:
1. User's device manual (PRIMARY - always cite first)
2. Clinical guidelines (ADA, NICE, etc.)
3. Research papers
4. General education
"""
    else:
        device_preamble = """
Note: The user has not uploaded device-specific documentation. Provide general guidance
and recommend they consult their specific device manual for detailed instructions.
"""

    # Build full prompt
    prompt = f"""{device_preamble}

USER QUERY: {query}

KNOWLEDGE CONTEXT:
{context}

INSTRUCTIONS:
- Synthesize a helpful, accurate response using the context above
- Cite sources with confidence scores
- For safety-critical information, always recommend consulting healthcare providers
- Keep response focused and actionable
"""
    return prompt
```

### Validation
- Print prompt output with and without user_devices parameter
- Verify device name appears in preamble

---

## Task 5: Pass Device Context Through Pipeline

### File to Modify
`agents/unified_agent.py`

### Location
`query_stream()` method (or main query handler)

### Implementation

Find the main query method and add device detection:

```python
async def query_stream(self, query: str, session_id: str = None):
    """Process query with device-aware context."""

    # Step 1: Detect user's devices
    user_devices = self.source_manager.get_user_devices()
    device_names = [d["name"] for d in user_devices]

    if device_names:
        logger.info(f"Detected user devices: {device_names}")
    else:
        logger.info("No user devices detected - using general guidance mode")

    # Step 2: Perform RAG search (existing logic)
    context = await self.search_knowledge_base(query)

    # Step 3: Build device-aware prompt
    prompt = self.build_prompt(query, context, user_devices=device_names)

    # Step 4: Generate response (existing logic)
    async for chunk in self.llm_provider.generate_text_stream(prompt):
        yield chunk
```

### Validation
- Check logs show "Detected user devices: [...]"
- Response should reference specific device by name

---

## Task 6: Reorder Sources Display

### File to Modify
`agents/unified_agent.py`

### Location
Response metadata construction (likely in `query_stream()` or a separate method)

### Implementation

```python
def _sort_sources(self, sources: List[Dict]) -> List[Dict]:
    """Sort sources with user devices first, then by confidence."""

    user_device_sources = []
    other_sources = []

    for source in sources:
        if source.get("is_user_device", False) or source.get("collection", "").startswith("user"):
            source["is_user_device"] = True
            user_device_sources.append(source)
        else:
            source["is_user_device"] = False
            other_sources.append(source)

    # Sort each group by confidence
    user_device_sources.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    other_sources.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    # User devices always first
    return user_device_sources + other_sources
```

Add to response metadata:

```python
# In query response construction
sources = self._sort_sources(raw_sources)
response_metadata = {
    "sources": sources,
    "user_devices_detected": [d["name"] for d in user_devices],
    # ... other metadata
}
```

### Validation
- API response shows user device sources first
- `is_user_device: true` flag present on user sources

---

## Task 7: Highlight User Device in Web UI

### File to Modify
`web/static/app.js`

### Location
Source rendering function (search for where sources are displayed)

### Implementation

```javascript
function renderSource(source, index) {
    const isUserDevice = source.is_user_device === true;
    const confidence = Math.round(source.confidence * 100);

    const className = isUserDevice ? 'source-item user-device-source' : 'source-item';
    const prefix = isUserDevice ? '⭐ YOUR DEVICE: ' : '';
    const sourceName = source.name || source.collection || 'Unknown Source';

    return `
        <div class="${className}">
            <span class="source-name">${prefix}${sourceName}</span>
            <span class="source-confidence">(${confidence}%)</span>
        </div>
    `;
}

// In the sources rendering loop:
const sourcesHtml = sources.map((s, i) => renderSource(s, i)).join('');
```

### File to Modify
`web/static/styles.css`

### Add Styling

```css
/* User device source highlighting */
.user-device-source {
    background-color: #f0f8f0;
    border-left: 4px solid #28a745;
    padding-left: 12px;
    font-weight: 600;
}

.user-device-source .source-name {
    color: #1e7e34;
}

.user-device-source .source-confidence {
    color: #28a745;
    font-weight: bold;
}

/* Ensure proper spacing */
.source-item {
    padding: 8px 12px;
    margin-bottom: 4px;
    border-radius: 4px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.source-item:not(.user-device-source) {
    background-color: #f8f9fa;
    border-left: 4px solid #dee2e6;
}
```

### Validation
- Upload a device PDF
- Ask a question
- User device should appear first with green highlight and star icon

---

## File Change Summary

| File | Action | Changes |
|------|--------|---------|
| `agents/researcher_chromadb.py` | Modify | Add USER_DEVICE_CONFIDENCE_BOOST, modify search_collection() |
| `agents/source_manager.py` | Modify | Add get_user_devices(), _detect_device_type() |
| `agents/unified_agent.py` | Modify | Update build_prompt(), query_stream(), add _sort_sources() |
| `web/static/app.js` | Modify | Update source rendering for user device highlight |
| `web/static/styles.css` | Modify | Add .user-device-source styling |
| `scripts/cleanup_community_collections.py` | Create | New script to delete community collections |
| `scripts/ingest_openaps_docs.py` | Delete | If exists |
| `scripts/ingest_loop_docs.py` | Delete | If exists |

---

## Testing Checklist

### Unit Tests
- [ ] `test_user_device_confidence_boost` - Verify +0.35 boost applied
- [ ] `test_get_user_devices_detection` - Verify device detection works
- [ ] `test_build_prompt_with_devices` - Verify device-aware prompt
- [ ] `test_source_sorting` - Verify user devices sorted first

### Integration Tests
- [ ] Upload PDF → Query → User device appears first with 95%+ confidence
- [ ] Query without user docs → General guidance mode
- [ ] Response uses "your [device]..." language

### Manual Testing
1. Delete community collections: `python scripts/cleanup_community_collections.py`
2. Upload CamAPS FX manual to `docs/user-sources/`
3. Run ingestion for user doc
4. Query: "how do I mitigate highs?"
5. Verify:
   - Response says "your CamAPS FX system..."
   - Sources show ⭐ YOUR DEVICE first
   - No OpenAPS/Loop/AndroidAPS references

---

## Execution Order

1. **Phase 1 (Cleanup)**: Task 1 - Remove community collections
2. **Phase 2 (Backend)**: Tasks 2, 3 - Boost + detection
3. **Validate**: Test search ranking returns user docs first
4. **Phase 3 (Synthesis)**: Tasks 4, 5 - Device-aware prompts
5. **Phase 4 (Display)**: Tasks 6, 7 - Source ordering + UI
6. **Final Validation**: End-to-end test with real device PDF

---

## Rollback Plan

If issues arise:
1. Remove USER_DEVICE_CONFIDENCE_BOOST constant (reverts to equal weighting)
2. Remove device_preamble from build_prompt (reverts to generic prompts)
3. CSS changes are non-breaking (just visual)
4. Community collections can be re-ingested if needed (keep scripts in git history)

---

## Session Resume Notes

When resuming implementation:
1. Read this plan
2. Start with `git status` to see current state
3. Begin with Task 1 (cleanup) - it's independent
4. Tasks 2-3 can be done in parallel
5. Tasks 4-5 depend on Task 3
6. Tasks 6-7 can be done after Task 5

**Key files to read first:**
- `agents/researcher_chromadb.py` - Understand current search implementation
- `agents/source_manager.py` - Understand current source management
- `agents/unified_agent.py` - Understand query pipeline and prompt building
