import pytest
from agents.llm_provider import ensure_gemini_prefix


def test_ensure_gemini_prefix_already_prefixed():
    """Test that already prefixed model names are returned as-is."""
    assert ensure_gemini_prefix("gemini/gemini-2.5-flash") == "gemini/gemini-2.5-flash"


def test_ensure_gemini_prefix_add_prefix():
    """Test adding prefix to model name without it."""
    assert ensure_gemini_prefix("gemini-2.5-flash") == "gemini/gemini-2.5-flash"


def test_ensure_gemini_prefix_empty_string():
    """Test that empty string raises ValueError."""
    with pytest.raises(ValueError, match="model_name cannot be empty or None"):
        ensure_gemini_prefix("")


def test_ensure_gemini_prefix_none():
    """Test that None raises ValueError."""
    with pytest.raises(ValueError, match="model_name cannot be empty or None"):
        ensure_gemini_prefix(None)


def test_ensure_gemini_prefix_other_model():
    """Test adding prefix to a non-Gemini model name."""
    assert ensure_gemini_prefix("some-other-model") == "gemini/some-other-model"