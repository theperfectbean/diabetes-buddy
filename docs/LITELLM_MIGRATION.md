# LiteLLM Migration Guide

This document describes the migration from `google-genai` SDK to `LiteLLM` for LLM operations in Diabetes Buddy.

## Why We Migrated

### Problems with google-genai SDK
1. **Single provider lock-in** - Only supports Google Gemini models
2. **No automatic retries** - Transient errors (503, timeouts) cause failures
3. **No routing control** - Can't verify if calls go to direct API vs Vertex AI

### Benefits of LiteLLM
1. **Multi-provider flexibility** - Supports Gemini, OpenAI, Anthropic, Ollama
2. **Unified interface** - Same code works across all providers
3. **Built-in retries** - Automatic retry with exponential backoff
4. **Defensive routing** - Verify and enforce direct Google AI Studio API

## What Changed

### Dependencies
```diff
- google-genai
+ litellm>=1.58.0
+ tenacity>=8.2.0
```

### New Components (`litellm_components.py`)

| Component | Purpose |
|-----------|---------|
| `ensure_gemini_prefix()` | Ensures model names have `gemini/` prefix |
| `detect_litellm_endpoint()` | Verifies routing to direct API vs Vertex AI |
| `retry_llm_call` | Tenacity decorator for automatic retries |
| `VertexAIRoutingError` | Exception for routing failures |

### Provider Architecture

```
LLMFactory.get_provider()
    │
    ├── provider = "gemini" or "litellm"
    │   │
    │   ├── Try: LiteLLMProvider (preferred)
    │   │   ├── Applies gemini/ prefix
    │   │   ├── Detects endpoint (must be direct_api)
    │   │   └── Raises VertexAIRoutingError if Vertex AI
    │   │
    │   └── Fallback: GeminiProvider (google-genai SDK)
    │
    └── provider = "openai", "anthropic", "ollama"
        └── Uses LitellmBasedProvider subclasses
```

## How to Verify Correct Routing

### Check Logs During Initialization

```bash
export $(grep -v '^#' .env | xargs)
python3 -c "
import logging
logging.basicConfig(level=logging.INFO)
from agents.llm_provider import LLMFactory
LLMFactory.reset_provider()
provider = LLMFactory.get_provider()
print('Provider:', type(provider).__name__)
"
```

Expected output:
```
INFO:root:LiteLLMProvider: Detecting endpoint for model gemini/gemini-2.5-flash...
INFO:root:Detected API base from response: https://generativelanguage.googleapis.com/v1beta/...
INFO:root:Detected direct Google AI Studio API endpoint from response metadata
INFO:root:LiteLLM provider initialized with direct Google AI Studio API
Provider: LiteLLMProvider
```

### Critical: Model Name Prefix

The `gemini/` prefix is **required** for direct API routing:

| Model Name | Routing | Rate Limits |
|------------|---------|-------------|
| `gemini/gemini-2.5-flash` | Direct API | **High** (1500 RPM) |
| `gemini-2.5-flash` | Vertex AI | **Low** (150 RPM) |

The `ensure_gemini_prefix()` function auto-corrects unprefixed names with a warning.

## Known Issues

### 1. ChromaDB Dimension Mismatch

**Symptom:**
```
Error querying collection: Collection expecting embedding with dimension of 384, got 768
```

**Cause:** Existing ChromaDB collections were built with 384-dimensional embeddings (e.g., `all-MiniLM-L6-v2`). New Gemini `text-embedding-004` produces 768 dimensions.

**Solution:** Rebuild ChromaDB collections:
```bash
rm -rf .cache/chromadb
python -m diabuddy  # Will rebuild with new embeddings
```

### 2. set_verbose Deprecation Warning

**Symptom:**
```
WARNING: `litellm.set_verbose` is deprecated. Please set `os.environ['LITELLM_LOG'] = 'DEBUG'`
```

**Impact:** Non-blocking, functionality works correctly.

**Future fix:** Update `detect_litellm_endpoint()` to use `LITELLM_LOG` environment variable.

## Adding Other Providers

### OpenAI

```bash
# .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

```bash
# requirements.txt - uncomment:
openai
```

### Anthropic

```bash
# .env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

```bash
# requirements.txt - uncomment:
anthropic
```

### Ollama (Local)

```bash
# .env
LLM_PROVIDER=ollama
OLLAMA_MODEL=ollama/mistral
```

No API key required - runs locally.

## Rollback Procedure

If LiteLLM causes issues, revert to google-genai SDK:

### 1. Force GeminiProvider

```python
# In your code
from agents.llm_provider import LLMFactory, GeminiProvider
LLMFactory.reset_provider()
LLMFactory._provider_instance = GeminiProvider()
```

### 2. Or set environment variable

```bash
# Force direct SDK access
LLM_PROVIDER=gemini-sdk
```

### 3. Full revert (if needed)

```bash
# Restore google-genai dependency
pip install google-genai
pip uninstall litellm tenacity

# Revert llm_provider.py to previous version
git checkout HEAD~1 -- agents/llm_provider.py
```

## Testing

### Run Component Tests

```bash
python -m pytest tests/test_llm_provider_switching.py -v
```

### Verify All Agents

```bash
export $(grep -v '^#' .env | xargs)

# Test each agent
python3 -c "from agents.safety import SafetyAuditor; print('Safety OK')"
python3 -c "from agents.triage import TriageAgent; print('Triage OK')"
python3 -c "from agents.data_ingestion import GlookoAnalyzer; print('Glooko OK')"
python3 -c "from agents.researcher_chromadb import ResearcherAgent; print('Researcher OK')"
```

## Performance Comparison

| Metric | google-genai | LiteLLM |
|--------|--------------|---------|
| Cold start | ~2s | ~5s (includes endpoint detection) |
| Text generation | ~1-2s | ~1-2s |
| Embeddings | ~0.5s | ~0.5s |
| Retry on 503 | Manual | Automatic (3 attempts) |
| Multi-provider | No | Yes |

## References

- [LiteLLM Documentation](https://docs.litellm.ai/)
- [LiteLLM Gemini Provider](https://docs.litellm.ai/docs/providers/gemini)
- [Tenacity Retry Library](https://tenacity.readthedocs.io/)
