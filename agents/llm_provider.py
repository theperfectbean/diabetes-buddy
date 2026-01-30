"""
LLM Provider Abstraction for Diabetes Buddy

Provides a provider-agnostic interface for LLM operations, supporting
multiple providers (Gemini, OpenAI, Anthropic, etc.) through a factory pattern.
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

# Import LiteLLM components from dedicated module
from litellm_components import (
    ensure_gemini_prefix,
    detect_litellm_endpoint,
    retry_llm_call,
    should_retry_llm_call,
    VertexAIRoutingError,
)

# Provider SDKs are imported lazily inside provider implementations


class LLMProviderType(Enum):
    """Supported LLM providers."""
    GEMINI = "gemini"
    LITELLM = "litellm"
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
    - `provider` is the provider name (eg. "gemini", "openai").
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


def _get_fallbacks_from_env() -> list[str]:
    raw = os.environ.get("FALLBACK_MODELS", "")
    if not raw:
        return []
    return [m.strip() for m in raw.split(",") if m.strip()]


def _get_num_retries_from_env() -> int:
    try:
        return int(os.environ.get("FALLBACK_RETRIES", "1"))
    except Exception:
        return 1


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


class LiteLLMProvider(LLMProvider):
    """
    Provider implementation using LiteLLM for Gemini API access.

    This provider routes Gemini calls through the direct Google AI Studio API
    (not Vertex AI) for higher rate limits and simpler authentication.
    """

    provider_name = "litellm"
    DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    DEFAULT_EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "text-embedding-004")

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
        skip_endpoint_detection: bool = False,
    ):
        """
        Initialize LiteLLM provider with Gemini routing validation.

        Args:
            api_key: Gemini API key (reads from GEMINI_API_KEY env var if not provided)
            model_name: Model to use for text generation
            embedding_model: Model to use for embeddings
            skip_endpoint_detection: Skip endpoint detection (for testing)

        Raises:
            LLMProviderError: If API key is not provided
            VertexAIRoutingError: If LiteLLM routes to Vertex AI instead of direct API
        """
        # Get API key
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise LLMProviderError(
                "Gemini API key not found. Set GEMINI_API_KEY environment variable "
                "or pass api_key parameter."
            )

        # Get and prefix model name
        raw_model = model_name or self.DEFAULT_MODEL
        self.model = ensure_gemini_prefix(raw_model)
        self.embedding_model = embedding_model or self.DEFAULT_EMBEDDING_MODEL

        # Store endpoint detection result
        self.endpoint_info: dict = {}

        # Detect endpoint ONCE during initialization
        if not skip_endpoint_detection:
            logging.info(f"LiteLLMProvider: Detecting endpoint for model {self.model}...")
            self.endpoint_info = detect_litellm_endpoint()

            if self.endpoint_info.get("endpoint") != "direct_api":
                detected = self.endpoint_info.get("endpoint", "unknown")
                raise VertexAIRoutingError(
                    message=(
                        f"LiteLLM is routing to {detected} instead of direct Google AI Studio API. "
                        "This will result in 10x lower rate limits. "
                        "Ensure GEMINI_API_KEY is set and model name has 'gemini/' prefix."
                    ),
                    model_name=self.model,
                    detected_endpoint=detected,
                )

            logging.info("LiteLLM provider initialized with direct Google AI Studio API")
        else:
            logging.info("LiteLLM provider initialized (endpoint detection skipped)")

    def generate_text(
        self,
        prompt: Union[str, list[str]],
        config: Optional[GenerationConfig] = None,
        file_reference: Optional[FileReference] = None,
    ) -> str:
        """
        Generate text using LiteLLM with Gemini models.

        Args:
            prompt: Text prompt or list of content parts
            config: Generation configuration
            file_reference: Optional file reference for multimodal input

        Returns:
            Generated text response

        Raises:
            LLMProviderError: If generation fails
        """
        return self._generate_text_with_retry(prompt, config, file_reference)

    @retry_llm_call
    def _generate_text_with_retry(
        self,
        prompt: Union[str, list[str]],
        config: Optional[GenerationConfig] = None,
        file_reference: Optional[FileReference] = None,
    ) -> str:
        """Internal method with retry decorator applied."""
        from litellm import completion

        config = config or GenerationConfig()

        # Build a single prompt string
        if isinstance(prompt, list):
            prompt_text = "\n".join(prompt)
        else:
            prompt_text = prompt

        # If a file reference is present, reference its id in the prompt
        if file_reference:
            prompt_text = f"[file:{file_reference.file_id}]\n" + (prompt_text or "")

        try:
            # Build completion parameters
            completion_kwargs = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt_text}],
                "api_key": self.api_key,
            }

            # Add optional parameters from config
            if config.temperature is not None:
                completion_kwargs["temperature"] = config.temperature
            if config.max_tokens is not None:
                completion_kwargs["max_tokens"] = config.max_tokens
            if config.top_p is not None:
                completion_kwargs["top_p"] = config.top_p
            if config.stop_sequences:
                completion_kwargs["stop"] = config.stop_sequences

            response = completion(**completion_kwargs)

            # Log usage
            _log_usage(self.provider_name, self.model, response, prompt_text)

            # Extract content from response
            try:
                choice = response.choices[0]
                msg = choice.message
                if hasattr(msg, "content"):
                    return msg.content.strip() if msg.content else ""
                return str(msg).strip()
            except (IndexError, AttributeError) as e:
                logging.warning(f"Unexpected response format: {e}")
                return str(response)

        except Exception as e:
            raise LLMProviderError(f"Text generation failed (litellm): {e}")

    def embed_text(
        self,
        text: Union[str, list[str]],
    ) -> Union[list[float], list[list[float]]]:
        """
        Generate embeddings using LiteLLM.

        Args:
            text: Text string or list of text strings

        Returns:
            Embedding vector(s)

        Raises:
            LLMProviderError: If embedding fails
        """
        is_single = isinstance(text, str)
        inputs = [text] if is_single else text

        try:
            from litellm import embedding as litellm_embedding

            # Prefix embedding model for Gemini - ALL models need gemini/ prefix for direct API
            embed_model = self.embedding_model
            if not embed_model.startswith("gemini/"):
                embed_model = f"gemini/{embed_model}"

            response = litellm_embedding(
                model=embed_model,
                input=inputs,
                api_key=self.api_key,
            )

            # Extract embeddings from response
            embeddings = []
            if hasattr(response, "data"):
                for item in response.data:
                    if isinstance(item, dict):
                        embeddings.append(item.get("embedding", []))
                    else:
                        embeddings.append(getattr(item, "embedding", []))
            elif isinstance(response, dict) and "data" in response:
                embeddings = [d.get("embedding", []) for d in response.get("data", [])]
            else:
                embeddings = response

            return embeddings[0] if is_single else embeddings

        except Exception as e:
            raise LLMProviderError(f"Embedding generation failed (litellm): {e}")

    def upload_file(
        self,
        file_path: Union[str, Path],
        display_name: Optional[str] = None,
    ) -> FileReference:
        """
        Upload a file (base64 encoded for LiteLLM).

        Args:
            file_path: Path to the file to upload
            display_name: Optional display name for the file

        Returns:
            FileReference with base64 encoded data

        Raises:
            LLMProviderError: If upload fails
        """
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
            raise LLMProviderError(f"File upload failed (litellm): {e}")

    def get_file(self, file_id: str) -> FileReference:
        """
        Retrieve a file reference by ID.

        Args:
            file_id: File identifier (path)

        Returns:
            FileReference object
        """
        return FileReference(
            file_id=file_id,
            display_name=None,
            mime_type=None,
            size_bytes=None,
            provider=self.provider_name,
            provider_data=None,
        )

    def get_model_info(self) -> ModelInfo:
        """
        Get information about the current model.

        Returns:
            ModelInfo with capabilities and metadata
        """
        # Model capabilities based on known Gemini models
        model_configs = {
            "gemini/gemini-2.5-flash": {
                "context_window": 1000000,
                "cost": 0.15,
            },
            "gemini/gemini-2.5-pro": {
                "context_window": 2000000,
                "cost": 1.25,
            },
            "gemini/gemini-1.5-flash": {
                "context_window": 1000000,
                "cost": 0.075,
            },
            "gemini/gemini-1.5-pro": {
                "context_window": 2000000,
                "cost": 1.25,
            },
        }

        config = model_configs.get(
            self.model,
            {"context_window": 1000000, "cost": None},
        )

        return ModelInfo(
            provider=self.provider_name,
            model_name=self.model,
            context_window=config["context_window"],
            supports_embeddings=True,
            supports_file_upload=True,
            cost_per_million_tokens=config["cost"],
        )


class GeminiProvider(LLMProvider):
    """Provider implementation for Google Gemini (google-genai).

    Uses the google-genai client when an API key is provided, and falls
    back to local sentence-transformers embeddings if the SDK surface
    for embeddings is not available.
    """

    provider_name = "gemini"
    DEFAULT_TEXT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    DEFAULT_EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "textembedding-gecko")

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ):
        """
        Initialize Gemini provider.

        Args:
            api_key: Gemini API key (reads from GEMINI_API_KEY env var if not provided)
            model_name: Model to use for text generation
            embedding_model: Model to use for embeddings

        Raises:
            LLMProviderError: If API key is not provided or invalid
        """
        # Get API key
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise LLMProviderError(
                "Gemini API key not found. Set GEMINI_API_KEY environment variable "
                "or pass api_key parameter."
            )

        # Lazy import Gemini SDK so core module stays importable without SDK
        try:
            from google import genai as _genai
            from google.genai import types as _types
            self._genai = _genai
            self._types = _types
        except Exception as e:
            raise LLMProviderError(
                f"google-genai SDK not available (install google-genai). {e}"
            )

        try:
            self.client = self._genai.Client(api_key=self.api_key)
        except Exception as e:
            raise LLMProviderError(f"Failed to initialize Gemini client: {e}")

        self.model_name = model_name or self.DEFAULT_TEXT_MODEL
        self.embedding_model = embedding_model or self.DEFAULT_EMBEDDING_MODEL

    def generate_text(
        self,
        prompt: Union[str, list[str]],
        config: Optional[GenerationConfig] = None,
        file_reference: Optional[Any] = None,
    ) -> str:
        """
        Generate text using Gemini models.

        Args:
            prompt: Text prompt or list of content parts
            config: Generation configuration
            file_reference: Optional Gemini File object for multimodal input

        Returns:
            Generated text response

        Raises:
            LLMProviderError: If generation fails
        """
        config = config or GenerationConfig()

        # Build a single prompt string
        if isinstance(prompt, list):
            prompt_text = "\n".join(prompt)
        else:
            prompt_text = prompt

        # If a file reference is present, reference its id in the prompt
        if file_reference:
            prompt_text = f"[file:{file_reference.file_id}]\n" + (prompt_text or "")

        # Use the google.genai client directly with API key to avoid
        # LiteLLM routing to Vertex/ADC paths when a simple API key is available.
        try:
            # Build parameters for SDK call
            sdk_kwargs = {}
            if config and config.temperature is not None:
                sdk_kwargs["temperature"] = float(config.temperature)
            if config and config.max_tokens is not None:
                # google genai uses max_output_tokens or similar; include common keys
                sdk_kwargs["max_output_tokens"] = int(config.max_tokens)

            # Use the genai models.generate_content API (keeps behavior similar to previous direct usage)
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[prompt_text],
                    **sdk_kwargs,
                )
            except TypeError as te:
                # Some google-genai versions don't accept extra kwargs (eg. temperature)
                # Retry without sdk kwargs to preserve compatibility.
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[prompt_text],
                )

            # Log usage if available
            try:
                _log_usage("gemini", self.model_name, response, prompt_text)
            except Exception:
                pass

            # Try common ways to extract generated text from the genai response
            # 1) response.text (simple wrapper)
            text = getattr(response, "text", None)
            if text:
                return str(text).strip()

            # 2) response.output -> content blocks
            try:
                out = getattr(response, "output", None)
                if out:
                    # output may be a list of objects with 'content' sequences
                    # Try to coerce into a string
                    if isinstance(out, (list, tuple)) and len(out) > 0:
                        first = out[0]
                        # content may be nested
                        cont = getattr(first, "content", None) or first
                        # If content is a list-like, join text pieces
                        if isinstance(cont, (list, tuple)) and len(cont) > 0:
                            parts = []
                            for c in cont:
                                t = getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else None)
                                if t:
                                    parts.append(t)
                            if parts:
                                return "".join(parts).strip()
                        # If content has text attribute
                        t = getattr(cont, "text", None)
                        if t:
                            return str(t).strip()
            except Exception:
                pass

            # 3) Fallback to stringifying the response
            return str(response)

        except Exception as e:
            raise LLMProviderError(f"Text generation failed (gemini genai): {e}")

    def embed_text(
        self,
        text: Union[str, list[str]],
    ) -> Union[list[float], list[list[float]]]:
        """
        Generate embeddings using Gemini embedding models.

        Args:
            text: Text string or list of text strings

        Returns:
            Embedding vector(s)

        Raises:
            LLMProviderError: If embedding fails
        """
        is_single = isinstance(text, str)
        inputs = [text] if is_single else text

        try:
            # Prefer direct google.genai embeddings API using the client with API key
            # This avoids LiteLLM selecting Vertex/ADC flows when the model name suggests Gemini
            # Some google-genai versions expose embeddings at module level rather
            # than as a method on the client instance. Prefer module-level call
            # but fall back to client if available.
            try:
                resp = self._genai.embeddings.create(model=self.embedding_model, input=inputs)
            except Exception:
                resp = self.client.embeddings.create(model=self.embedding_model, input=inputs)

            embeddings = None
            # common response shape: resp.data -> list of {"embedding": [...]}
            if hasattr(resp, "data"):
                embeddings = [ (d.get("embedding") if isinstance(d, dict) else getattr(d, "embedding", None)) for d in resp.data ]
            elif isinstance(resp, dict) and "data" in resp:
                embeddings = [d.get("embedding") for d in resp.get("data", [])]
            else:
                embeddings = resp

            return embeddings[0] if is_single else embeddings
        except AttributeError as e:
            # Fall back to a local embedding model if available (sentence-transformers)
            try:
                from sentence_transformers import SentenceTransformer
                model_name = os.environ.get("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
                model = SentenceTransformer(model_name)
                import numpy as _np
                arr = model.encode(inputs, convert_to_numpy=True)
                # Normalize to list-of-lists robustly for scalars, 1D, or 2D arrays
                if isinstance(arr, _np.ndarray):
                    if arr.ndim == 0:
                        embeddings = [[float(arr)]]
                    elif arr.ndim == 1:
                        embeddings = [arr.tolist()]
                    else:
                        embeddings = arr.tolist()
                elif isinstance(arr, (list, tuple)):
                    # ensure inner items are lists
                    embeddings = [list(a) if not isinstance(a, (float, int)) else [float(a)] for a in arr]
                else:
                    # fallback: coerce single value
                    embeddings = [[float(arr)]]

                return embeddings[0] if is_single else embeddings
            except Exception as ex:
                raise LLMProviderError(
                    "Embedding API not available in the installed google-genai SDK and local "
                    "sentence-transformers fallback failed or is not installed. "
                    "Install `sentence-transformers` or provide ADC credentials to enable Gemini embeddings. "
                    f"Original error: {e}; fallback error: {ex}"
                )
        except Exception as e:
            raise LLMProviderError(f"Embedding generation failed (gemini genai): {e}")

    def upload_file(
        self,
        file_path: Union[str, Path],
        display_name: Optional[str] = None,
    ) -> FileReference:
        """
        Upload a file to Gemini File API.

        Args:
            file_path: Path to the file to upload
            display_name: Optional display name for the file

        Returns:
            Gemini File object

        Raises:
            LLMProviderError: If upload fails
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise LLMProviderError(f"File not found: {file_path}")

        try:
            config = self._types.UploadFileConfig(
                display_name=display_name or file_path.name,
            )

            gemini_file = self.client.files.upload(
                file=str(file_path),
                config=config,
            )

            # Wait for processing
            import time
            while gemini_file.state.name == "PROCESSING":
                time.sleep(2)
                gemini_file = self.client.files.get(name=gemini_file.name)

            if gemini_file.state.name != "ACTIVE":
                raise LLMProviderError(
                    f"File processing failed with state: {gemini_file.state.name}"
                )

            return FileReference(
                file_id=getattr(gemini_file, "name", str(gemini_file)),
                display_name=getattr(gemini_file, "display_name", display_name or file_path.name),
                mime_type=getattr(gemini_file, "mime_type", None),
                size_bytes=getattr(gemini_file, "size_bytes", None),
                provider="gemini",
                provider_data=gemini_file,
            )

        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(f"File upload failed: {e}")

    def get_file(self, file_id: str) -> FileReference:
        """
        Retrieve a previously uploaded file.

        Args:
            file_id: Gemini file name/ID

        Returns:
            Gemini File object

        Raises:
            LLMProviderError: If retrieval fails
        """
        try:
            gemini_file = self.client.files.get(name=file_id)
            return FileReference(
                file_id=getattr(gemini_file, "name", file_id),
                display_name=getattr(gemini_file, "display_name", None),
                mime_type=getattr(gemini_file, "mime_type", None),
                size_bytes=getattr(gemini_file, "size_bytes", None),
                provider="gemini",
                provider_data=gemini_file,
            )
        except Exception as e:
            raise LLMProviderError(f"File retrieval failed: {e}")

    def get_model_info(self) -> ModelInfo:
        """
        Get information about the current Gemini model.

        Returns:
            ModelInfo with capabilities and metadata
        """
        # Model capabilities based on known Gemini models
        model_configs = {
            "gemini-2.5-flash": {
                "context_window": 1000000,
                "cost": 0.15,  # per million tokens (approximate)
            },
            "gemini-2.5-pro": {
                "context_window": 2000000,
                "cost": 1.25,  # per million tokens (approximate)
            },
            "gemini-1.5-flash": {
                "context_window": 1000000,
                "cost": 0.075,
            },
            "gemini-1.5-pro": {
                "context_window": 2000000,
                "cost": 1.25,
            },
        }

        config = model_configs.get(
            self.model_name,
            {"context_window": 1000000, "cost": None},
        )

        return ModelInfo(
            provider="gemini",
            model_name=self.model_name,
            context_window=config["context_window"],
            supports_embeddings=True,
            supports_file_upload=True,
            cost_per_million_tokens=config["cost"],
        )


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

        fallbacks = _get_fallbacks_from_env()
        num_retries = _get_num_retries_from_env()

        try:
            from litellm import completion

            response = completion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                fallbacks=fallbacks or None,
                num_retries=num_retries,
                api_key=self.api_key,
            )

            _log_usage(self.provider_name, self.model_name, response, prompt_text)

            # extract content
            try:
                choice = response.choices[0]
                msg = getattr(choice, "message", None)
                if msg and isinstance(msg, dict):
                    return msg.get("content", "").strip()
                return getattr(choice, "text", "").strip()
            except Exception:
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


class LLMFactory:
    """
    Factory for creating LLM provider instances.

    Reads LLM_PROVIDER from environment variables and returns the
    appropriate provider instance with fallback logic.
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
            provider_type: Provider type ("gemini", "litellm", "openai", etc.)
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
        provider_str = (provider_type or os.environ.get("LLM_PROVIDER", "gemini")).lower().strip()

        # For "gemini" or "litellm", try LiteLLMProvider first with fallback to GeminiProvider
        if provider_str in ("gemini", "litellm"):
            try:
                logging.info(f"Attempting to initialize LiteLLMProvider for provider={provider_str}")
                cls._provider_instance = LiteLLMProvider(**kwargs)
                logging.info("LiteLLMProvider initialized successfully")
                return cls._provider_instance
            except VertexAIRoutingError as e:
                # LiteLLM routing issue - fall back to google-genai SDK
                logging.warning(
                    f"LiteLLM routing to Vertex AI detected, falling back to google-genai SDK: {e}"
                )
                try:
                    cls._provider_instance = GeminiProvider(**kwargs)
                    logging.info("Fallback to GeminiProvider (google-genai SDK) successful")
                    return cls._provider_instance
                except Exception as fallback_error:
                    raise LLMProviderError(
                        f"LiteLLM routing failed and google-genai fallback also failed. "
                        f"LiteLLM error: {e}. Fallback error: {fallback_error}"
                    )
            except LLMProviderError as e:
                # Other LiteLLM initialization error - try fallback
                logging.warning(f"LiteLLMProvider initialization failed, trying GeminiProvider: {e}")
                try:
                    cls._provider_instance = GeminiProvider(**kwargs)
                    logging.info("Fallback to GeminiProvider (google-genai SDK) successful")
                    return cls._provider_instance
                except Exception as fallback_error:
                    raise LLMProviderError(
                        f"Both LiteLLMProvider and GeminiProvider failed. "
                        f"LiteLLM error: {e}. Fallback error: {fallback_error}"
                    )
            except Exception as e:
                # Unexpected error - try fallback
                logging.warning(f"Unexpected error initializing LiteLLMProvider: {e}")
                try:
                    cls._provider_instance = GeminiProvider(**kwargs)
                    logging.info("Fallback to GeminiProvider (google-genai SDK) successful")
                    return cls._provider_instance
                except Exception as fallback_error:
                    raise LLMProviderError(
                        f"Both LiteLLMProvider and GeminiProvider failed. "
                        f"Original error: {e}. Fallback error: {fallback_error}"
                    )

        # For other providers, use the registry
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
# Note: "gemini" and "litellm" are handled specially in get_provider()
LLMFactory.register_provider("gemini-sdk", GeminiProvider)  # Direct SDK access
LLMFactory.register_provider("openai", OpenAIProvider)
LLMFactory.register_provider("anthropic", AnthropicProvider)
LLMFactory.register_provider("ollama", OllamaProvider)


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
