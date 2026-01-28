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

from google import genai
from google.genai import types


class LLMProviderType(Enum):
    """Supported LLM providers."""
    GEMINI = "gemini"
    # Future providers can be added here:
    # OPENAI = "openai"
    # ANTHROPIC = "anthropic"
    # OLLAMA = "ollama"


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
            Provider-specific file reference object

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
            Provider-specific file reference object

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


class GeminiProvider(LLMProvider):
    """
    Google Gemini LLM provider implementation.
    
    Wraps google.generativeai SDK to provide a consistent interface.
    """

    # Default models
    DEFAULT_TEXT_MODEL = "gemini-2.5-flash"
    DEFAULT_EMBEDDING_MODEL = "models/gemini-embedding-001"

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

        try:
            self.client = genai.Client(api_key=self.api_key)
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

        # Build contents list
        if file_reference:
            # Include file in the prompt
            if isinstance(prompt, str):
                contents = [file_reference, prompt]
            else:
                contents = [file_reference] + prompt
        else:
            contents = [prompt] if isinstance(prompt, str) else prompt

        try:
            # Build generation config
            gen_config = types.GenerateContentConfig(
                temperature=config.temperature,
                max_output_tokens=config.max_tokens,
                top_p=config.top_p,
                top_k=config.top_k,
                stop_sequences=config.stop_sequences,
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=gen_config,
            )

            return response.text.strip()

        except Exception as e:
            raise LLMProviderError(f"Text generation failed: {e}")

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
        texts = [text] if is_single else text

        try:
            result = self.client.models.embed_content(
                model=self.embedding_model,
                contents=texts,
            )

            embeddings = [emb.values for emb in result.embeddings]

            return embeddings[0] if is_single else embeddings

        except Exception as e:
            raise LLMProviderError(f"Embedding generation failed: {e}")

    def upload_file(
        self,
        file_path: Union[str, Path],
        display_name: Optional[str] = None,
    ) -> types.File:
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
            config = types.UploadFileConfig(
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

            return gemini_file

        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(f"File upload failed: {e}")

    def get_file(self, file_id: str) -> types.File:
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
            return self.client.files.get(name=file_id)
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


class LLMFactory:
    """
    Factory for creating LLM provider instances.
    
    Reads LLM_PROVIDER from environment variables and returns the
    appropriate provider instance with fallback logic.
    """

    _provider_instance: Optional[LLMProvider] = None

    @classmethod
    def get_provider(
        cls,
        provider_type: Optional[str] = None,
        **kwargs,
    ) -> LLMProvider:
        """
        Get or create an LLM provider instance.

        Args:
            provider_type: Provider type ("gemini", "openai", etc.)
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
        provider_str = provider_type or os.environ.get("LLM_PROVIDER", "gemini")
        provider_str = provider_str.lower().strip()

        try:
            provider_enum = LLMProviderType(provider_str)
        except ValueError:
            supported = ", ".join(p.value for p in LLMProviderType)
            raise LLMProviderError(
                f"Unsupported LLM provider: {provider_str}. "
                f"Supported providers: {supported}"
            )

        # Create provider instance
        try:
            if provider_enum == LLMProviderType.GEMINI:
                cls._provider_instance = GeminiProvider(**kwargs)
            else:
                raise LLMProviderError(
                    f"Provider {provider_str} not yet implemented"
                )

            return cls._provider_instance

        except Exception as e:
            # Fallback logic: try Gemini as default
            if provider_enum != LLMProviderType.GEMINI:
                try:
                    print(f"Warning: Failed to initialize {provider_str}, falling back to Gemini")
                    cls._provider_instance = GeminiProvider(**kwargs)
                    return cls._provider_instance
                except Exception as fallback_error:
                    raise LLMProviderError(
                        f"Failed to initialize both {provider_str} and fallback Gemini provider. "
                        f"Original error: {e}. Fallback error: {fallback_error}"
                    )
            else:
                raise LLMProviderError(f"Failed to initialize Gemini provider: {e}")

    @classmethod
    def reset_provider(cls):
        """
        Reset the cached provider instance.
        
        Useful for testing or when switching providers at runtime.
        """
        cls._provider_instance = None


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
