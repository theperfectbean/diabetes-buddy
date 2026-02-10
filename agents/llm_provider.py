"""
LLM Provider Abstraction for Diabetes Buddy

Provides a provider-agnostic interface for LLM operations, supporting
Groq-first usage with optional local embeddings.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union
import json
from datetime import datetime
import logging

# Import LiteLLM components from local module

# Provider SDKs are imported lazily inside provider implementations


class LLMProviderType(Enum):
    """Supported LLM providers."""
    GROQ = "groq"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


@dataclass
class GenerationConfig:
    """Configuration for text generation."""
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop_sequences: Optional[list[str]] = None


@dataclass
class ModelInfo:
    """Information about a model."""
    provider: str
    model_name: str
    context_window: int
    supports_embeddings: bool
    supports_file_upload: bool
    cost_per_million_tokens: Optional[float] = None


@dataclass
class FileReference:
    """Provider-agnostic file reference/handle.

    - `file_id` is a provider-unique identifier (or local path for non-persistent uploads).
    - `provider` is the provider name (eg. "groq", "openai").
    - `provider_data` holds the original provider object or encoded bytes as needed.
    """
    file_id: str
    display_name: Optional[str]
    mime_type: Optional[str]
    size_bytes: Optional[int]
    provider: str
    provider_data: Any = None


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All provider implementations must inherit from this class and implement
    the required methods for text generation, embeddings, and file handling.
    """

    @abstractmethod
    def generate_text(
        self,
        prompt: Union[str, list[str]],
        config: Optional[GenerationConfig] = None,
        file_reference: Optional[Any] = None,
    ) -> str:
        """
        Generate text from a prompt.

        Args:
            prompt: Text prompt or list of prompts
            config: Generation configuration (temperature, max_tokens, etc.)
            file_reference: Optional file reference for multimodal input

        Returns:
            Generated text response

        Raises:
            LLMProviderError: If generation fails
        """
        pass

    @abstractmethod
    def generate_text_stream(
        self,
        prompt: Union[str, list[str]],
        config: Optional[GenerationConfig] = None,
        file_reference: Optional[Any] = None,
    ):
        """
        Generate text from a prompt with streaming.

        Args:
            prompt: Text prompt or list of prompts
            config: Generation configuration (temperature, max_tokens, etc.)
            file_reference: Optional file reference for multimodal input

        Yields:
            str: Chunks of generated text as they become available

        Raises:
            LLMProviderError: If generation fails
        """
        pass

    @abstractmethod
    def embed_text(
        self,
        text: Union[str, list[str]],
    ) -> Union[list[float], list[list[float]]]:
        """
        Generate embeddings for text.

        Args:
            text: Text string or list of text strings

        Returns:
            Embedding vector(s) - single list for one text, list of lists for multiple

        Raises:
            LLMProviderError: If embedding fails
            NotImplementedError: If provider doesn't support embeddings
        """
        pass

    @abstractmethod
    def upload_file(
        self,
        file_path: Union[str, Path],
        display_name: Optional[str] = None,
    ) -> Any:
        """
        Upload a file for use in prompts.

        Args:
            file_path: Path to the file to upload
            display_name: Optional display name for the file

        Returns:
            Provider-agnostic :class:`FileReference` object (wraps provider data)

        Raises:
            LLMProviderError: If upload fails
            NotImplementedError: If provider doesn't support file uploads
        """
        pass

    @abstractmethod
    def get_file(self, file_id: str) -> Any:
        """
        Retrieve a previously uploaded file.

        Args:
            file_id: Provider-specific file identifier

        Returns:
            Provider-agnostic :class:`FileReference` object (wraps provider data)

        Raises:
            LLMProviderError: If retrieval fails
        """
        pass

    @abstractmethod
    def get_model_info(self) -> ModelInfo:
        """
        Get information about the current model.

        Returns:
            ModelInfo with capabilities and metadata
        """
        pass


class LLMProviderError(Exception):
    """Exception raised for LLM provider errors."""
    pass


def _log_usage(provider: str, model: str, response: Any, prompt: str) -> None:
    """Log usage statistics from LLM response if available."""
    try:
        usage = getattr(response, "usage", None)
        if usage:
            logging.debug(
                f"LLM Usage [{provider}/{model}]: "
                f"prompt_tokens={getattr(usage, 'prompt_tokens', 'N/A')}, "
                f"completion_tokens={getattr(usage, 'completion_tokens', 'N/A')}, "
                f"total_tokens={getattr(usage, 'total_tokens', 'N/A')}"
            )
    except Exception:
        pass


class LitellmBasedProvider(LLMProvider):
    """Base provider that uses LiteLLM for completion and embeddings.

    Concrete providers should set `provider_name`, `default_model`, and
    `default_embedding_model` class attributes and provide `api_key`.
    """

    provider_name: str = "litellm"
    default_model: str = "gpt-3.5-turbo"
    default_embedding_model: Optional[str] = None

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None, embedding_model: Optional[str] = None):
        self.api_key = api_key
        self.model_name = model_name or os.environ.get("PRIMARY_MODEL", self.default_model)
        self.embedding_model = embedding_model or os.environ.get("EMBEDDING_MODEL", self.default_embedding_model)

    def generate_text(self, prompt: Union[str, list[str]], config: Optional[GenerationConfig] = None, file_reference: Optional[FileReference] = None) -> str:
        config = config or GenerationConfig()
        if isinstance(prompt, list):
            prompt_text = "\n".join(prompt)
        else:
            prompt_text = prompt

        if file_reference:
            prompt_text = f"[file:{file_reference.file_id}]\n" + (prompt_text or "")


        try:
            from litellm import completion

            response = completion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                api_key=self.api_key,
            )

            _log_usage(self.provider_name, self.model_name, response, prompt_text)

            # extract content
            try:
                choice = response.choices[0]
                msg = getattr(choice, "message", None)
                if msg and isinstance(msg, dict):
                    content = msg.get("content", "").strip()
                    logging.info(f"[LLM] Response from dict: content len={len(content)}")
                    return content
                text_content = getattr(choice, "text", "").strip()
                logging.info(f"[LLM] Response from text field: content len={len(text_content)}")
                return text_content
            except Exception as e:
                logging.error(f"[LLM] Error extracting response: {e}")
                return str(response)

        except Exception as e:
            raise LLMProviderError(f"Text generation failed ({self.provider_name}): {e}")

    def embed_text(self, text: Union[str, list[str]]) -> Union[list[float], list[list[float]]]:
        if not self.embedding_model:
            raise LLMProviderError(f"Provider {self.provider_name} does not support embeddings")

        is_single = isinstance(text, str)
        inputs = [text] if is_single else text
        try:
            from litellm import embedding as _embedding
            resp = _embedding(model=self.embedding_model, input=inputs, api_key=self.api_key)
            if hasattr(resp, "data"):
                embeddings = [d.get("embedding") if isinstance(d, dict) else getattr(d, "embedding", None) for d in resp.data]
            elif isinstance(resp, dict) and "data" in resp:
                embeddings = [d.get("embedding") for d in resp.get("data", [])]
            else:
                embeddings = resp
            return embeddings[0] if is_single else embeddings
        except Exception as e:
            raise LLMProviderError(f"Embedding failed ({self.provider_name}): {e}")

    def upload_file(self, file_path: Union[str, Path], display_name: Optional[str] = None) -> FileReference:
        file_path = Path(file_path)
        if not file_path.exists():
            raise LLMProviderError(f"File not found: {file_path}")
        try:
            import base64
            data = file_path.read_bytes()
            encoded = base64.b64encode(data).decode("utf-8")
            return FileReference(
                file_id=str(file_path),
                display_name=display_name or file_path.name,
                mime_type=None,
                size_bytes=file_path.stat().st_size,
                provider=self.provider_name,
                provider_data=encoded,
            )
        except Exception as e:
            raise LLMProviderError(f"upload_file failed ({self.provider_name}): {e}")

    def get_file(self, file_id: str) -> FileReference:
        return FileReference(file_id=file_id, display_name=None, mime_type=None, size_bytes=None, provider=self.provider_name, provider_data=None)

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(
            provider=self.provider_name,
            model_name=self.model_name,
            context_window=int(os.environ.get("MODEL_CONTEXT_WINDOW", "65536")),
            supports_embeddings=bool(self.embedding_model),
            supports_file_upload=True,
            cost_per_million_tokens=None,
        )


class OpenAIProvider(LitellmBasedProvider):
    provider_name = "openai"
    default_model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    default_embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")


class AnthropicProvider(LitellmBasedProvider):
    provider_name = "anthropic"
    default_model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    default_embedding_model = None


class OllamaProvider(LitellmBasedProvider):
    provider_name = "ollama"
    default_model = os.environ.get("OLLAMA_MODEL", "ollama/mistral")
    default_embedding_model = None


class GroqProvider(LitellmBasedProvider):
    """Provider implementation for Groq API using LiteLLM.

    Groq provides fast, affordable open-source models via their API.
    Supports gpt-oss-20b and gpt-oss-120b models with optional prompt caching.
    """

    provider_name = "groq"
    default_model = os.environ.get("GROQ_MODEL", os.environ.get("GROQ_PRIMARY_MODEL", "groq/openai/gpt-oss-20b"))
    default_embedding_model = None  # Groq doesn't support embeddings

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
        enable_caching: bool = False,
    ):
        """
        Initialize Groq provider.

        Args:
            api_key: Groq API key (reads from GROQ_API_KEY env var if not provided)
            model_name: Model name (e.g., "groq/openai/gpt-oss-20b" or "groq/openai/gpt-oss-120b")
            embedding_model: Not supported for Groq
            enable_caching: Enable prompt caching if supported (50% input token discount)

        Raises:
            LLMProviderError: If API key is not provided
        """
        # Get Groq API key
        api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise LLMProviderError(
                "Groq API key not found. Set GROQ_API_KEY environment variable "
                "or pass api_key parameter."
            )

        # Initialize parent
        super().__init__(api_key=api_key, model_name=model_name)

        # Groq doesn't support embeddings
        if embedding_model:
            logging.warning("Groq does not support embeddings. embedding_model will be ignored.")

        self.enable_caching = enable_caching or os.environ.get("GROQ_ENABLE_CACHING", "false").lower() == "true"
        self.model_configs = self._load_model_configs()
        self.token_usage = {"input": 0, "output": 0}

        logging.info(f"GroqProvider initialized with model {self.model_name}, caching={self.enable_caching}")

    def _load_model_configs(self) -> dict:
        """Load Groq model configuration from models.json."""
        try:
            config_path = Path(__file__).parent.parent / "config" / "models.json"
            with open(config_path) as f:
                models_data = json.load(f)
                groq_models = models_data.get("models", {}).get("groq", {})
                return groq_models
        except Exception as e:
            logging.warning(f"Failed to load Groq model configs: {e}")
            return {}

    def get_model_config(self, model_name: Optional[str] = None) -> dict:
        """Get configuration for a Groq model."""
        model = model_name or self.model_name
        # Extract model short name (e.g., "gpt-oss-20b" from "groq/openai/gpt-oss-20b")
        short_name = model.split("/")[-1] if "/" in model else model
        return self.model_configs.get(short_name, {})

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model_name: Optional[str] = None
    ) -> float:
        """
        Calculate cost for tokens using Groq pricing from models.json.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model_name: Model name (uses default if not provided)

        Returns:
            Estimated cost in USD
        """
        config = self.get_model_config(model_name)
        input_cost = config.get("cost_per_million_input_tokens", 0)
        output_cost = config.get("cost_per_million_output_tokens", 0)

        # Apply caching discount if enabled (50% discount on cached input tokens)
        # For simplicity, assume 50% of input tokens are from cache (conservative estimate)
        if self.enable_caching and config.get("supports_prompt_caching"):
            cache_discount = config.get("prompt_caching_input_discount", 0.5)
            input_cost_with_cache = input_cost * (1 - (cache_discount * 0.5))
        else:
            input_cost_with_cache = input_cost

        total_cost = (input_tokens / 1_000_000) * input_cost_with_cache + (output_tokens / 1_000_000) * output_cost
        return total_cost

    def generate_text(
        self,
        prompt: Union[str, list[str]],
        config: Optional[GenerationConfig] = None,
        file_reference: Optional[FileReference] = None,
    ) -> str:
        """
        Generate text using Groq API via LiteLLM.

        Args:
            prompt: Text prompt or list of prompts
            config: Generation configuration
            file_reference: Not supported for Groq (file_upload=false)

        Returns:
            Generated text response

        Raises:
            LLMProviderError: If generation fails
        """
        if file_reference:
            logging.warning("Groq does not support file uploads. file_reference will be ignored.")

        config = config or GenerationConfig()

        # Build prompt text
        if isinstance(prompt, list):
            prompt_text = "\n".join(prompt)
        else:
            prompt_text = prompt

        try:
            from litellm import completion

            # Prepare completion kwargs
            completion_kwargs = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt_text}],
            }

            # Disable extended thinking for Groq (use reasoning field)
            # Note: Groq does not officially support extended_thinking, but LiteLLM may route it
            # We explicitly set reasoning configuration if needed
            if hasattr(config, 'reasoning_mode'):
                # If reasoning_mode is explicitly set, use it; otherwise default to disabled
                pass  # Let it through if explicitly configured
            else:
                # Disable extended thinking to ensure content field is used
                logging.debug("[GROQ] Extended thinking not explicitly configured, defaulting to standard mode")

            # Add API key for Groq
            if self.api_key:
                completion_kwargs["api_key"] = self.api_key

            # Add generation config parameters
            if config.temperature is not None:
                completion_kwargs["temperature"] = config.temperature
            if config.max_tokens is not None:
                completion_kwargs["max_tokens"] = config.max_tokens
            if config.top_p is not None:
                completion_kwargs["top_p"] = config.top_p
            if config.stop_sequences:
                completion_kwargs["stop"] = config.stop_sequences

            # Call Groq API via LiteLLM
            response = completion(**completion_kwargs)

            # Track token usage
            if hasattr(response, "usage"):
                self.token_usage["input"] += response.usage.prompt_tokens
                self.token_usage["output"] += response.usage.completion_tokens

            _log_usage(self.provider_name, self.model_name, response, prompt_text)

            # Extract content from response
            try:
                choice = response.choices[0]
                msg = choice.message
                
                # ALWAYS check content first - this is the ideal case
                if hasattr(msg, "content") and msg.content and msg.content.strip():
                    content = msg.content.strip()
                    logging.info(f"[GROQ] Using content field: {len(content)} chars")
                    return content

                # Fallback: reasoning models sometimes put output in reasoning field
                if hasattr(msg, "reasoning") and msg.reasoning and msg.reasoning.strip():
                    reasoning = msg.reasoning.strip()
                    logging.warning(f"[GROQ] Content empty, falling back to reasoning field: {len(reasoning)} chars")
                    return reasoning

                # Both fields empty - treat as failure
                logging.error("[GROQ] Content and reasoning fields both empty in response")
                raise LLMProviderError("Groq returned empty content")
                
            except (IndexError, AttributeError) as e:
                logging.error(f"[GROQ] Failed to extract response: {e}")
                raise LLMProviderError(f"Groq response parse failed: {e}")

        except Exception as e:
            error_msg = str(e)
            logging.error(f"Groq text generation failed: {error_msg}")
            raise LLMProviderError(f"Groq text generation failed: {e}")

    def generate_text_stream(
        self,
        prompt: Union[str, list[str]],
        config: Optional[GenerationConfig] = None,
        file_reference: Optional[FileReference] = None,
    ):
        """
        Generate text from a prompt with streaming using Groq API.

        Args:
            prompt: Text prompt or list of prompts
            config: Generation configuration
            file_reference: Not supported for Groq

        Yields:
            str: Chunks of generated text as they become available

        Raises:
            LLMProviderError: If generation fails
        """
        if file_reference:
            logging.warning("Groq does not support file uploads. file_reference will be ignored.")

        config = config or GenerationConfig()

        # Build prompt text
        if isinstance(prompt, list):
            prompt_text = "\n".join(prompt)
        else:
            prompt_text = prompt

        try:
            from litellm import completion

            # Prepare completion kwargs with streaming
            completion_kwargs = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt_text}],
                "stream": True,
            }

            # Add API key for Groq
            if self.api_key:
                completion_kwargs["api_key"] = self.api_key

            # Add generation config parameters
            if config.temperature is not None:
                completion_kwargs["temperature"] = config.temperature
            if config.max_tokens is not None:
                completion_kwargs["max_tokens"] = config.max_tokens
            if config.top_p is not None:
                completion_kwargs["top_p"] = config.top_p
            if config.stop_sequences:
                completion_kwargs["stop"] = config.stop_sequences

            # Stream from Groq API via LiteLLM
            response_stream = completion(**completion_kwargs)

            has_content_chunks = False
            reasoning_buffer = []

            for chunk in response_stream:
                try:
                    if hasattr(chunk, "choices") and chunk.choices:
                        choice = chunk.choices[0]
                        if hasattr(choice, "delta") and choice.delta:
                            delta = choice.delta
                            # ALWAYS prefer content over reasoning
                            if hasattr(delta, "content") and delta.content:
                                has_content_chunks = True
                                yield delta.content
                            # Buffer reasoning as fallback in case content never arrives
                            elif hasattr(delta, "reasoning") and delta.reasoning:
                                reasoning_buffer.append(delta.reasoning)
                        elif hasattr(choice, "message") and choice.message:
                            msg = choice.message
                            if hasattr(msg, "content") and msg.content:
                                has_content_chunks = True
                                yield msg.content
                            elif hasattr(msg, "reasoning") and msg.reasoning:
                                reasoning_buffer.append(msg.reasoning)
                except (IndexError, AttributeError) as e:
                    logging.warning(f"[GROQ] Unexpected chunk format: {e}")
                    continue

            # Fallback: if no content was streamed, yield buffered reasoning
            if not has_content_chunks and reasoning_buffer:
                fallback = "".join(reasoning_buffer)
                logging.warning(f"[GROQ] No content in stream, falling back to reasoning: {len(fallback)} chars")
                yield fallback

        except Exception as e:
            logging.error(f"[GROQ] Streaming failed: {e}")
            raise LLMProviderError(f"Groq streaming failed: {e}")

    def embed_text(
        self,
        text: Union[str, list[str]],
    ) -> Union[list[float], list[list[float]]]:
        """
        Generate embeddings locally for Groq-only workflows.

        Args:
            text: Text string or list of text strings

        Returns:
            Embedding vector(s)
        """
        is_single = isinstance(text, str)
        inputs = [text] if is_single else text

        try:
            from sentence_transformers import SentenceTransformer
            import numpy as _np

            model_name = os.environ.get(
                "EMBEDDING_MODEL",
                os.environ.get("LOCAL_EMBEDDING_MODEL", "all-mpnet-base-v2"),
            )
            model = SentenceTransformer(model_name)
            arr = model.encode(inputs, convert_to_numpy=True)

            if isinstance(arr, _np.ndarray):
                if arr.ndim == 1:
                    embeddings = [arr.tolist()]
                else:
                    embeddings = arr.tolist()
            else:
                embeddings = arr

            return embeddings[0] if is_single else embeddings
        except Exception as e:
            raise LLMProviderError(
                "Local embedding generation failed. Install `sentence-transformers` "
                "or set LOCAL_EMBEDDING_MODEL to a valid model. "
                f"Original error: {e}"
            )

    def upload_file(self, file_path: Union[str, Path], display_name: Optional[str] = None) -> FileReference:
        """File upload not supported for Groq."""
        raise LLMProviderError("Groq does not support file uploads.")

    def get_file(self, file_id: str) -> FileReference:
        """File retrieval not supported for Groq."""
        raise LLMProviderError("Groq does not support file retrieval.")

    def get_model_info(self) -> ModelInfo:
        """Get information about the current Groq model."""
        config = self.get_model_config()
        return ModelInfo(
            provider=self.provider_name,
            model_name=self.model_name,
            context_window=config.get("context_window", 128000),
            supports_embeddings=True,
            supports_file_upload=False,
            cost_per_million_tokens=config.get("cost_per_million_input_tokens"),
        )


class LLMFactory:
    """
    Factory for creating LLM provider instances.

    Reads LLM_PROVIDER from environment variables and returns the
    appropriate provider instance.
    """

    _provider_instance: Optional[LLMProvider] = None
    _provider_registry: dict = {}

    @classmethod
    def register_provider(cls, name: str, provider_class):
        cls._provider_registry[name.lower()] = provider_class

    @classmethod
    def get_provider(
        cls,
        provider_type: Optional[str] = None,
        **kwargs,
    ) -> LLMProvider:
        """
        Get or create an LLM provider instance.

        Args:
            provider_type: Provider type ("groq", "openai", etc.)
                          Reads from LLM_PROVIDER env var if not provided
            **kwargs: Provider-specific configuration options

        Returns:
            Configured LLM provider instance

        Raises:
            LLMProviderError: If provider initialization fails
        """
        # Return cached instance if available (singleton pattern)
        if cls._provider_instance is not None:
            return cls._provider_instance

        # Determine provider type
        provider_str = (provider_type or os.environ.get("LLM_PROVIDER", "groq")).lower().strip()

        # For providers, use the registry
        provider_class = cls._provider_registry.get(provider_str)
        if not provider_class:
            supported = ", ".join(sorted(cls._provider_registry.keys()))
            raise LLMProviderError(f"Unsupported provider: {provider_str}. Supported: {supported}")

        try:
            cls._provider_instance = provider_class(**kwargs)
            return cls._provider_instance
        except Exception as e:
            raise LLMProviderError(f"Failed to initialize provider {provider_str}: {e}")

    @classmethod
    def reset_provider(cls):
        """
        Reset the cached provider instance.

        Useful for testing or when switching providers at runtime.
        """
        cls._provider_instance = None


# Register built-in providers (do this after class definitions)
LLMFactory.register_provider("openai", OpenAIProvider)
LLMFactory.register_provider("anthropic", AnthropicProvider)
LLMFactory.register_provider("ollama", OllamaProvider)
LLMFactory.register_provider("groq", GroqProvider)


# Convenience functions for common operations
def get_llm() -> LLMProvider:
    """Get the configured LLM provider instance."""
    return LLMFactory.get_provider()


def generate_text(prompt: str, **kwargs) -> str:
    """
    Generate text using the configured LLM provider.

    Args:
        prompt: Text prompt
        **kwargs: Additional generation parameters

    Returns:
        Generated text
    """
    llm = get_llm()
    config = GenerationConfig(**kwargs) if kwargs else None
    return llm.generate_text(prompt, config=config)


def embed_text(text: Union[str, list[str]]) -> Union[list[float], list[list[float]]]:
    """
    Generate embeddings using the configured LLM provider.

    Args:
        text: Text string or list of text strings

    Returns:
        Embedding vector(s)
    """
    llm = get_llm()
    return llm.embed_text(text)
