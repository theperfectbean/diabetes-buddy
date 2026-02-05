import os
from agents.llm_provider import LLMFactory, GroqProvider


def test_factory_defaults_to_groq_provider():
    """Factory should default to Groq provider when no provider specified."""
    os.environ["GROQ_API_KEY"] = "test-api-key"
    LLMFactory.reset_provider()

    provider = LLMFactory.get_provider()

    assert isinstance(provider, GroqProvider)


