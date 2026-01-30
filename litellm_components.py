"""
LiteLLM Components for Diabetes Buddy

This module provides utility functions and classes for working with LiteLLM,
including routing validation, retry logic, and error handling for Gemini API calls.
"""

import logging
import os
import tenacity
from datetime import datetime
from typing import Any, Dict


def ensure_gemini_prefix(model_name: str) -> str:
    """
    Ensures that Gemini model names have the required "gemini/" prefix for LiteLLM routing.

    LiteLLM routes "gemini/model-name" to direct Google AI Studio API, while "model-name" alone
    goes through Vertex AI with 10x lower rate limits. This function prevents misconfigurations.

    Args:
        model_name (str): The model name to check and potentially prefix.

    Returns:
        str: The model name with "gemini/" prefix if it was missing.

    Raises:
        ValueError: If model_name is empty or None.

    Examples:
        >>> ensure_gemini_prefix("gemini-2.5-flash")
        'gemini/gemini-2.5-flash'

        >>> ensure_gemini_prefix("gemini/gemini-1.5-pro")
        'gemini/gemini-1.5-pro'

        >>> ensure_gemini_prefix("")
        Traceback (most recent call last):
            ...
        ValueError: model_name cannot be empty or None
    """
    if not model_name:
        raise ValueError("model_name cannot be empty or None")
    if model_name.startswith("gemini/"):
        return model_name
    else:
        logging.warning(f"Auto-correcting model name '{model_name}' to 'gemini/{model_name}' for LiteLLM routing")
        return f"gemini/{model_name}"


def detect_litellm_endpoint() -> Dict[str, Any]:
    """
    Detects whether LiteLLM is routing Gemini calls to direct Google AI Studio API or Vertex AI.

    This function makes a test API call with verbose logging enabled and parses the logs
    to determine the endpoint being used. Direct API uses https://generativelanguage.googleapis.com,
    while Vertex AI uses different endpoints.

    Returns:
        dict: {
            "endpoint": "direct_api" | "vertex_ai" | "unknown",
            "verified": bool,  # True if endpoint was successfully detected
            "test_succeeded": bool  # True if the API call succeeded without errors
        }
    """
    import litellm
    from litellm import completion

    # Enable verbose logging to capture API call details
    # Using environment variable instead of deprecated litellm.set_verbose
    original_log_level = os.environ.get('LITELLM_LOG', '')
    os.environ['LITELLM_LOG'] = 'DEBUG'

    # Set up log capture to parse verbose output
    log_capture = []
    class LogCapture(logging.Handler):
        def emit(self, record):
            log_capture.append(self.format(record))

    # Get the litellm logger and add our capture handler
    litellm_logger = logging.getLogger('litellm')
    original_level = litellm_logger.level
    litellm_logger.setLevel(logging.DEBUG)
    capture_handler = LogCapture()
    litellm_logger.addHandler(capture_handler)

    endpoint = "unknown"
    verified = False
    test_succeeded = False

    try:
        # Make test API call with minimal parameters to avoid rate limits
        response = completion(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )
        test_succeeded = True

        # Parse captured logs for URL patterns
        logs_text = "\n".join(log_capture)
        logging.info(f"LiteLLM detection logs: {logs_text}")

        # Also check response metadata for API base
        api_base = None
        if hasattr(response, '_hidden_params') and 'api_base' in response._hidden_params:
            api_base = response._hidden_params['api_base']
            logging.info(f"Detected API base from response: {api_base}")

        # Detection logic: Check response api_base first, then logs
        if api_base:
            if "generativelanguage.googleapis.com" in api_base:
                endpoint = "direct_api"
                verified = True
                logging.info("Detected direct Google AI Studio API endpoint from response metadata")
            elif "vertex" in api_base.lower() or "aiplatform" in api_base.lower():
                endpoint = "vertex_ai"
                verified = True
                logging.info("Detected Vertex AI endpoint from response metadata")
        elif "generativelanguage.googleapis.com" in logs_text:
            # Direct Google AI Studio API endpoint detected
            endpoint = "direct_api"
            verified = True
            logging.info("Detected direct Google AI Studio API endpoint from logs")
        elif "vertex" in logs_text.lower() or "aiplatform" in logs_text.lower():
            # Vertex AI endpoint patterns detected
            endpoint = "vertex_ai"
            verified = True
            logging.info("Detected Vertex AI endpoint from logs")
        else:
            # Could not find recognizable endpoint patterns
            logging.warning("Could not detect endpoint from logs or response metadata")

    except Exception as e:
        # API call failed - could be due to missing keys, network issues, etc.
        logging.error(f"Test API call failed: {e}")
        test_succeeded = False
    finally:
        # Clean up logging configuration to avoid side effects
        litellm_logger.removeHandler(capture_handler)
        litellm_logger.setLevel(original_level)
        # Restore original log level
        if original_log_level:
            os.environ['LITELLM_LOG'] = original_log_level
        else:
            os.environ.pop('LITELLM_LOG', None)

    return {
        "endpoint": endpoint,
        "verified": verified,
        "test_succeeded": test_succeeded
    }


def should_retry_llm_call(exception):
    """Check if an exception should trigger a retry for LLM API calls."""
    if isinstance(exception, (ConnectionError, TimeoutError)):
        return True
    msg = str(exception).lower()
    return "503" in msg or "unavailable" in msg


def _log_and_raise(exception):
    """Log final failure and re-raise the exception."""
    logging.error("All retries exhausted")
    raise exception


def retry_llm_call(func):
    """Tenacity retry decorator for LLM API calls with exponential backoff."""
    return tenacity.retry(
        retry=tenacity.retry_if_exception(should_retry_llm_call),
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=lambda retry_state: logging.warning(
            f"Retry attempt {retry_state.attempt_number}/3 due to: {retry_state.outcome.exception()}"
        ),
        retry_error_callback=lambda retry_state: _log_and_raise(retry_state.outcome.exception()),
        reraise=True
    )(func)


class VertexAIRoutingError(Exception):
    """
    Exception raised when LiteLLM incorrectly routes Gemini calls through Vertex AI
    instead of the direct Google AI Studio API.

    This indicates a configuration issue that should be addressed to avoid
    rate limiting and higher costs.
    """

    def __init__(self, message: str, model_name: str, detected_endpoint: str):
        """
        Initialize the exception.

        Args:
            message: Description of the routing error
            model_name: The model name that was incorrectly routed
            detected_endpoint: The detected endpoint ("vertex_ai" or "unknown")
        """
        super().__init__(message)
        self.message = message
        self.model_name = model_name
        self.detected_endpoint = detected_endpoint

    def __str__(self) -> str:
        """Return a formatted error message."""
        return (
            f"VertexAIRoutingError: {self.message}\n"
            f"Model: {self.model_name}\n"
            f"Detected Endpoint: {self.detected_endpoint}\n"
            f"Expected: direct_api (Google AI Studio)\n"
            f"Solution: Ensure model name starts with 'gemini/' for LiteLLM routing"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return exception details as a dictionary for logging."""
        return {
            "error_type": "VertexAIRoutingError",
            "message": self.message,
            "model_name": self.model_name,
            "detected_endpoint": self.detected_endpoint,
            "expected_endpoint": "direct_api",
            "timestamp": datetime.now().isoformat()
        }