"""
Tests for LiteLLM Components

Comprehensive test suite for all LiteLLM utility functions and classes.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from litellm_components import (
    ensure_gemini_prefix,
    detect_litellm_endpoint,
    retry_llm_call,
    should_retry_llm_call,
    VertexAIRoutingError
)


# Tests for ensure_gemini_prefix
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


# Tests for detect_litellm_endpoint
@patch('litellm.completion')
@patch('litellm.set_verbose')
def test_detect_litellm_endpoint_direct_api(mock_set_verbose, mock_completion):
    """Test detection of direct API endpoint."""
    mock_response = MagicMock()
    mock_response._hidden_params = {'api_base': 'https://generativelanguage.googleapis.com/v1beta'}
    mock_completion.return_value = mock_response

    result = detect_litellm_endpoint()
    assert result['endpoint'] == 'direct_api'
    assert result['verified'] is True
    assert result['test_succeeded'] is True


@patch('litellm.completion')
@patch('litellm.set_verbose')
def test_detect_litellm_endpoint_vertex_ai(mock_set_verbose, mock_completion):
    """Test detection of Vertex AI endpoint."""
    mock_response = MagicMock()
    mock_response._hidden_params = {'api_base': 'https://vertexai.googleapis.com/v1'}
    mock_completion.return_value = mock_response

    result = detect_litellm_endpoint()
    assert result['endpoint'] == 'vertex_ai'
    assert result['verified'] is True
    assert result['test_succeeded'] is True


@patch('litellm.completion')
@patch('litellm.set_verbose')
def test_detect_litellm_endpoint_api_failure(mock_set_verbose, mock_completion):
    """Test handling of API call failure."""
    mock_completion.side_effect = Exception("API Error")

    result = detect_litellm_endpoint()
    assert result['endpoint'] == 'unknown'
    assert result['verified'] is False
    assert result['test_succeeded'] is False


# Tests for retry functionality
def test_should_retry_llm_call_connection_error():
    """Test that ConnectionError triggers retry."""
    assert should_retry_llm_call(ConnectionError("Connection failed")) is True


def test_should_retry_llm_call_timeout_error():
    """Test that TimeoutError triggers retry."""
    assert should_retry_llm_call(TimeoutError("Request timed out")) is True


def test_should_retry_llm_call_503_error():
    """Test that 503 error message triggers retry."""
    assert should_retry_llm_call(Exception("503 Service Unavailable")) is True


def test_should_retry_llm_call_unavailable_error():
    """Test that unavailable error message triggers retry."""
    assert should_retry_llm_call(Exception("Service temporarily unavailable")) is True


def test_should_retry_llm_call_other_error():
    """Test that other errors do not trigger retry."""
    assert should_retry_llm_call(ValueError("Invalid input")) is False


@patch('time.sleep')  # Mock sleep to speed up tests
def test_retry_llm_call_success(mock_sleep):
    """Test successful retry after failures."""
    call_count = 0

    @retry_llm_call
    def mock_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError('503 Service Unavailable')
        return 'success'

    result = mock_function()
    assert result == 'success'
    assert call_count == 3
    assert mock_sleep.call_count == 2  # Two retries, so two sleeps


@patch('time.sleep')
def test_retry_llm_call_exhaustion(mock_sleep):
    """Test retry exhaustion after max attempts."""
    @retry_llm_call
    def mock_function():
        raise ConnectionError('503 Service Unavailable')

    with pytest.raises(ConnectionError, match='503 Service Unavailable'):
        mock_function()

    assert mock_sleep.call_count == 2  # Two retries before giving up


# Tests for VertexAIRoutingError
def test_vertex_ai_routing_error_creation():
    """Test VertexAIRoutingError creation and attributes."""
    error = VertexAIRoutingError(
        "Routing error occurred",
        "gemini-2.5-flash",
        "vertex_ai"
    )

    assert error.message == "Routing error occurred"
    assert error.model_name == "gemini-2.5-flash"
    assert error.detected_endpoint == "vertex_ai"


def test_vertex_ai_routing_error_str():
    """Test VertexAIRoutingError string representation."""
    error = VertexAIRoutingError(
        "Test error",
        "gemini-2.5-flash",
        "vertex_ai"
    )

    str_repr = str(error)
    assert "VertexAIRoutingError: Test error" in str_repr
    assert "Model: gemini-2.5-flash" in str_repr
    assert "Detected Endpoint: vertex_ai" in str_repr
    assert "Expected: direct_api" in str_repr
    assert "Solution:" in str_repr


def test_vertex_ai_routing_error_to_dict():
    """Test VertexAIRoutingError to_dict method."""
    error = VertexAIRoutingError(
        "Test error",
        "gemini-2.5-flash",
        "vertex_ai"
    )

    dict_repr = error.to_dict()
    assert dict_repr['error_type'] == 'VertexAIRoutingError'
    assert dict_repr['message'] == 'Test error'
    assert dict_repr['model_name'] == 'gemini-2.5-flash'
    assert dict_repr['detected_endpoint'] == 'vertex_ai'
    assert dict_repr['expected_endpoint'] == 'direct_api'
    assert 'timestamp' in dict_repr

    # Verify it's JSON serializable
    json_str = json.dumps(dict_repr)
    assert json_str is not None


def test_vertex_ai_routing_error_inheritance():
    """Test that VertexAIRoutingError properly inherits from Exception."""
    error = VertexAIRoutingError("Test", "model", "endpoint")

    assert isinstance(error, Exception)
    assert isinstance(error, VertexAIRoutingError)