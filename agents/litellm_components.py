"""
LiteLLM helper utilities for Groq-only usage.

Provides retry logic for transient LLM API errors.
"""

import logging
import tenacity


def should_retry_llm_call(exception: Exception) -> bool:
    """Return True if an exception should trigger a retry."""
    if isinstance(exception, (ConnectionError, TimeoutError)):
        return True
    msg = str(exception).lower()
    return "503" in msg or "unavailable" in msg or "timeout" in msg


def _log_and_raise(exception: Exception) -> None:
    """Log final failure and re-raise the exception."""
    logging.error("All retries exhausted")
    raise exception


def retry_llm_call(func):
    """Tenacity retry decorator for LLM API calls with exponential backoff."""
    return tenacity.retry(
        retry=tenacity.retry_if_exception(should_retry_llm_call),
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
        before_sleep=lambda retry_state: logging.warning(
            f"Retry attempt {retry_state.attempt_number}/3 due to: {retry_state.outcome.exception()}"
        ),
        retry_error_callback=lambda retry_state: _log_and_raise(
            retry_state.outcome.exception()
        ),
        reraise=True,
    )(func)


class VertexAIRoutingError(Exception):
    """Deprecated routing error placeholder."""
    pass

    def to_dict(self):
        """Return exception details as a dictionary for logging."""
        return {}
