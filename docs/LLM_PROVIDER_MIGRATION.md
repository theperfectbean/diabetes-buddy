# LLM Provider Abstraction - Migration Guide

## Overview

The Diabetes Buddy project has been refactored to be LLM-agnostic, replacing direct Google Gemini dependencies with a flexible provider abstraction layer. This allows future support for multiple LLM providers (OpenAI, Anthropic, Ollama, etc.) while maintaining full backward compatibility with existing Gemini functionality.

## What Changed

### New Files

1. **`agents/llm_provider.py`** - Core abstraction layer
   - `LLMProvider` - Abstract base class defining the provider interface
   - `GeminiProvider` - Gemini implementation wrapping google.generativeai
   - `LLMFactory` - Factory for instantiating providers based on configuration
   - Helper functions: `get_llm()`, `generate_text()`, `embed_text()`

2. **`config/models.json`** - Model capabilities reference
   - Cost information per million tokens
   - Context window sizes
   - Feature support (embeddings, file upload, vision)
   - Usage recommendations for different tasks

### Modified Files

1. **`agents/triage.py`**
   - Replaced `from google import genai` with `from .llm_provider import LLMFactory, GenerationConfig`
   - Changed `self.client = genai.Client(...)` to `self.llm = LLMFactory.get_provider()`
   - Updated `generate_content()` calls to `llm.generate_text()`

2. **`agents/researcher.py`**
   - Same pattern as triage.py
   - File upload now uses `llm.upload_file()`
   - File retrieval uses `llm.get_file()`

3. **`agents/researcher_chromadb.py`**
   - Updated embeddings to use `llm.embed_text()`
   - Text generation uses `llm.generate_text()`

4. **`.env.example`**
   - Added `LLM_PROVIDER=gemini` configuration
   - Included placeholders for future providers

5. **`requirements.txt`**
   - Marked google-genai as optional for future multi-provider support
   - Added commented lines for future providers

## Configuration

### Environment Variables

```bash
# .env file
LLM_PROVIDER=gemini  # Currently only 'gemini' is supported
GEMINI_API_KEY=your-api-key-here
```

### Provider Selection

The system reads `LLM_PROVIDER` from environment variables and instantiates the appropriate provider. If not specified, it defaults to Gemini.

```python
from agents.llm_provider import LLMFactory

# Get the configured provider (singleton)
llm = LLMFactory.get_provider()

# Or specify explicitly
llm = LLMFactory.get_provider(provider_type="gemini")
```

## API Reference

### LLMProvider Interface

All provider implementations must support these methods:

#### `generate_text(prompt, config=None, file_reference=None) -> str`

Generate text from a prompt.

```python
from agents.llm_provider import get_llm, GenerationConfig

llm = get_llm()

# Simple generation
response = llm.generate_text("What is diabetes?")

# With configuration
config = GenerationConfig(
    temperature=0.7,
    max_tokens=1000,
    top_p=0.9
)
response = llm.generate_text("Explain insulin resistance", config=config)

# With file reference (for multimodal input)
file_ref = llm.upload_file("document.pdf")
response = llm.generate_text(
    prompt="Summarize this document",
    file_reference=file_ref
)
```

#### `embed_text(text) -> list[float] | list[list[float]]`

Generate embeddings for semantic search.

```python
llm = get_llm()

# Single text
embedding = llm.embed_text("diabetes management")
# Returns: [0.123, -0.456, ...]

# Multiple texts
embeddings = llm.embed_text([
    "insulin sensitivity",
    "blood glucose levels",
    "carb counting"
])
# Returns: [[0.123, ...], [0.456, ...], [0.789, ...]]
```

#### `upload_file(file_path, display_name=None) -> Any`

Upload a file for use in prompts (multimodal).

```python
llm = get_llm()

file_ref = llm.upload_file(
    file_path="docs/manual.pdf",
    display_name="User Manual"
)

# Use in prompt
response = llm.generate_text(
    prompt="What does this manual say about insulin pumps?",
    file_reference=file_ref
)
```

#### `get_file(file_id) -> Any`

Retrieve a previously uploaded file.

```python
llm = get_llm()
file_ref = llm.get_file(file_id="files/abc123")
```

#### `get_model_info() -> ModelInfo`

Get information about the current model.

```python
llm = get_llm()
info = llm.get_model_info()

print(f"Provider: {info.provider}")
print(f"Model: {info.model_name}")
print(f"Context window: {info.context_window:,} tokens")
print(f"Supports embeddings: {info.supports_embeddings}")
print(f"Cost: ${info.cost_per_million_tokens}/M tokens")
```

### GenerationConfig

Configuration for text generation:

```python
@dataclass
class GenerationConfig:
    temperature: float = 0.7  # Randomness (0.0 = deterministic, 1.0 = creative)
    max_tokens: Optional[int] = None  # Maximum output length
    top_p: Optional[float] = None  # Nucleus sampling threshold
    top_k: Optional[int] = None  # Top-k sampling
    stop_sequences: Optional[list[str]] = None  # Stop generation at these strings
```

## Migration Examples

### Before (Direct Gemini)

```python
import os
from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)
model_name = "gemini-2.5-flash"

response = client.models.generate_content(
    model=model_name,
    contents=["What is insulin resistance?"]
)
print(response.text)
```

### After (Provider Abstraction)

```python
from agents.llm_provider import get_llm, GenerationConfig

llm = get_llm()  # Reads LLM_PROVIDER from environment

response = llm.generate_text(
    prompt="What is insulin resistance?",
    config=GenerationConfig(temperature=0.7)
)
print(response)
```

## Error Handling

The abstraction includes comprehensive error handling:

```python
from agents.llm_provider import LLMFactory, LLMProviderError

try:
    llm = LLMFactory.get_provider()
    response = llm.generate_text("Test query")
except LLMProviderError as e:
    print(f"Provider error: {e}")
    # Handle gracefully
```

Errors are wrapped in `LLMProviderError` with descriptive messages:
- API key missing or invalid
- Model initialization failures
- Generation/embedding errors
- File upload/retrieval errors

## Adding New Providers

To add support for a new provider (e.g., OpenAI):

1. **Create provider class in `llm_provider.py`:**

```python
class OpenAIProvider(LLMProvider):
    def __init__(self, api_key=None, model_name=None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise LLMProviderError("OPENAI_API_KEY not found")
        
        import openai
        self.client = openai.OpenAI(api_key=self.api_key)
        self.model_name = model_name or "gpt-4o"
    
    def generate_text(self, prompt, config=None, file_reference=None):
        # Implementation
        pass
    
    def embed_text(self, text):
        # Implementation
        pass
    
    # ... implement other methods
```

2. **Update `LLMProviderType` enum:**

```python
class LLMProviderType(Enum):
    GEMINI = "gemini"
    OPENAI = "openai"  # Add new provider
```

3. **Update `LLMFactory.get_provider()`:**

```python
if provider_enum == LLMProviderType.OPENAI:
    cls._provider_instance = OpenAIProvider(**kwargs)
```

4. **Update `.env.example`:**

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your-key-here
```

5. **Add model info to `config/models.json`**

## Testing

All existing functionality remains intact. To test:

```bash
# Make sure .env has LLM_PROVIDER=gemini and GEMINI_API_KEY set
cd /home/gary/diabetes-buddy
source .venv/bin/activate

# Test triage agent
python -m agents.triage

# Test researcher agent
python -m agents.researcher

# Test with MCP server
python mcp_server.py
```

## Benefits

1. **Future-proof**: Easy to add new LLM providers without changing agent code
2. **Provider flexibility**: Switch providers by changing one environment variable
3. **Cost optimization**: Use different providers for different tasks based on cost/performance
4. **Vendor independence**: Not locked into a single provider
5. **Clean architecture**: Separation of concerns between business logic and LLM provider
6. **Error handling**: Unified error handling across providers
7. **Type safety**: Full type hints and documentation

## Backward Compatibility

✅ **All existing Gemini functionality works unchanged**
- Same API responses
- Same model performance
- Same caching behavior
- Same file upload/processing
- Same embedding generation

The refactoring is a pure architectural change with zero breaking changes to functionality.

## Troubleshooting

### "LLM_PROVIDER not set" or defaults to Gemini

- The system defaults to `gemini` if `LLM_PROVIDER` is not set
- This is intentional for backward compatibility

### "GEMINI_API_KEY not found"

- Make sure `.env` file exists and contains `GEMINI_API_KEY=your-key`
- Load environment: `python-dotenv` should load it automatically

### Provider initialization fails

- Check that the API key is valid
- Ensure network connectivity
- Review error messages for specific issues

### File upload issues

- GeminiProvider wraps the existing file upload logic
- Files must be under 20MB for Gemini
- Check `get_model_info()` for provider-specific limits

## Future Roadmap

### Phase 2: OpenAI Support (planned)
- Add `OpenAIProvider` class
- Support GPT-4 and GPT-4o models
- Use OpenAI embeddings API

### Phase 3: Anthropic/Claude Support (planned)
- Add `AnthropicProvider` class
- Support Claude 3.5 Sonnet and Haiku
- Implement Anthropic's message API

### Phase 4: Local Models (planned)
- Add `OllamaProvider` for local inference
- Support Llama, Mistral, and other open models
- Zero API costs for local deployment

### Phase 5: Hybrid Strategies (future)
- Use cheap models for classification
- Use premium models for synthesis
- Automatic fallback on rate limits
- Load balancing across providers

## Resources

- Provider abstraction: [agents/llm_provider.py](../agents/llm_provider.py)
- Model capabilities: [config/models.json](../config/models.json)
- Configuration: [.env.example](../.env.example)
- Gemini docs: https://ai.google.dev/gemini-api/docs
