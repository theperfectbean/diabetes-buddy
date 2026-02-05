import os
import sys
from pathlib import Path
import pytest
# Ensure project root is on sys.path when running pytest directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.llm_provider import LLMFactory, LLMProvider, LLMProviderError, GenerationConfig


class MockProvider(LLMProvider):
    def __init__(self, **kwargs):
        self.initialized_with = kwargs

    def generate_text(self, prompt, config=None, file_reference=None):
        return f"mocked-response: {prompt}"

    def embed_text(self, text):
        if isinstance(text, str):
            return [0.1, 0.2, 0.3]
        return [[0.1, 0.2, 0.3] for _ in text]

    def upload_file(self, file_path, display_name=None):
        return None

    def get_file(self, file_id: str):
        return None

    def get_model_info(self):
        return None


class BrokenProvider(LLMProvider):
    def __init__(self, **kwargs):
        raise RuntimeError("init-failure")

    def generate_text(self, *a, **k):
        raise RuntimeError()

    def embed_text(self, *a, **k):
        raise RuntimeError()

    def upload_file(self, *a, **k):
        raise RuntimeError()

    def get_file(self, *a, **k):
        raise RuntimeError()

    def get_model_info(self):
        raise RuntimeError()


def test_factory_returns_registered_provider_and_generate_embed():
    # Backup registry + instance
    orig_registry = LLMFactory._provider_registry.copy()
    LLMFactory.reset_provider()
    try:
        LLMFactory.register_provider("mock", MockProvider)

        # explicit provider selection
        p = LLMFactory.get_provider(provider_type="mock")
        assert isinstance(p, MockProvider)

        # generate_text
        out = p.generate_text("hello")
        assert out == "mocked-response: hello"

        # embed_text single and multiple
        e1 = p.embed_text("one")
        assert isinstance(e1, list) and len(e1) == 3
        e2 = p.embed_text(["a", "b"])
        assert isinstance(e2, list) and len(e2) == 2
    finally:
        # restore registry and reset
        LLMFactory._provider_registry = orig_registry
        LLMFactory.reset_provider()


def test_factory_raises_on_init_failure():
    orig_registry = LLMFactory._provider_registry.copy()
    LLMFactory.reset_provider()
    try:
        LLMFactory.register_provider("broken", BrokenProvider)

        with pytest.raises(LLMProviderError, match="Failed to initialize provider"):
            LLMFactory.get_provider(provider_type="broken")
    finally:
        LLMFactory._provider_registry = orig_registry
        LLMFactory.reset_provider()


def test_reset_provider_allows_reselection():
    orig_registry = LLMFactory._provider_registry.copy()
    LLMFactory.reset_provider()
    try:
        LLMFactory.register_provider("mock", MockProvider)
        p1 = LLMFactory.get_provider(provider_type="mock")
        assert isinstance(p1, MockProvider)

        # Reset and re-register different provider
        LLMFactory.reset_provider()
        LLMFactory.register_provider("mock", MockProvider)
        p2 = LLMFactory.get_provider(provider_type="mock")
        assert isinstance(p2, MockProvider)
        assert p1 is not p2
    finally:
        LLMFactory._provider_registry = orig_registry
        LLMFactory.reset_provider()
