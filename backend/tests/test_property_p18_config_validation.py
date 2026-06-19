# Feature: rag-chatbot-application, Property 18: Configuration validation rejects out-of-range parameters
"""
Property-based tests for P18: Configuration validation rejects out-of-range parameters.

**Validates: Requirements 5.8, 5.9, 5.10**

For any configuration in which any parameter is outside its defined valid range,
the Configuration Manager must reject the entire configuration and return a
ConfigurationError that names the specific failing parameter.
"""

import copy

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.app.config.configuration_manager import ConfigurationError, ConfigurationManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_raw_config() -> dict:
    """Return a known-good raw configuration dict to use as a mutation baseline."""
    return {
        "prompt_templates": {"system_instructions": "You are a helpful assistant."},
        "chunking": {
            "chunk_size_tokens": 400,
            "overlap_percentage": 12.0,
            "enable_contextual_summaries": True,
        },
        "models": {
            "llm_model_name": "openai/gpt-4o",
            "embedding_model_name": "openai/text-embedding-3-small",
        },
        "reranker": {
            "reranker_provider": "cohere",
            "reranker_model_name": "rerank-english-v3.0",
            "reranker_top_k": 5,
        },
        "retrieval": {
            "top_k": 20,
            "similarity_threshold": 0.7,
            "max_chunks_evaluated": 100,
            "prompt_max_chars": 8000,
        },
    }


# ---------------------------------------------------------------------------
# P18 – Property tests
# ---------------------------------------------------------------------------


# Feature: rag-chatbot-application, Property 18: Configuration validation rejects out-of-range parameters
@given(
    invalid_chunk_size=st.integers().filter(lambda x: x < 300 or x > 500)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p18_invalid_chunk_size_tokens_rejected(invalid_chunk_size: int) -> None:
    """P18: chunk_size_tokens outside [300, 500] must raise ConfigurationError naming the field.

    **Validates: Requirements 5.8, 5.9, 5.10**
    """
    raw = _valid_raw_config()
    raw["chunking"]["chunk_size_tokens"] = invalid_chunk_size

    with pytest.raises(ConfigurationError) as exc_info:
        ConfigurationManager._validate(raw)

    error: ConfigurationError = exc_info.value
    assert "chunk_size_tokens" in error.parameter, (
        f"Expected 'chunk_size_tokens' in error.parameter, got {error.parameter!r} "
        f"for invalid value {invalid_chunk_size}"
    )


# Feature: rag-chatbot-application, Property 18: Configuration validation rejects out-of-range parameters
@given(
    invalid_overlap=st.floats(allow_nan=False, allow_infinity=False).filter(
        lambda x: x < 10.0 or x > 15.0
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p18_invalid_overlap_percentage_rejected(invalid_overlap: float) -> None:
    """P18: overlap_percentage outside [10.0, 15.0] must raise ConfigurationError naming the field.

    **Validates: Requirements 5.8, 5.9, 5.10**
    """
    raw = _valid_raw_config()
    raw["chunking"]["overlap_percentage"] = invalid_overlap

    with pytest.raises(ConfigurationError) as exc_info:
        ConfigurationManager._validate(raw)

    error: ConfigurationError = exc_info.value
    assert "overlap_percentage" in error.parameter, (
        f"Expected 'overlap_percentage' in error.parameter, got {error.parameter!r} "
        f"for invalid value {invalid_overlap}"
    )


# Feature: rag-chatbot-application, Property 18: Configuration validation rejects out-of-range parameters
@given(
    invalid_top_k=st.integers().filter(lambda x: x < 1 or x > 20)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p18_invalid_reranker_top_k_rejected(invalid_top_k: int) -> None:
    """P18: reranker_top_k outside [1, 20] must raise ConfigurationError naming the field.

    **Validates: Requirements 5.8, 5.9, 5.10**
    """
    raw = _valid_raw_config()
    raw["reranker"]["reranker_top_k"] = invalid_top_k

    with pytest.raises(ConfigurationError) as exc_info:
        ConfigurationManager._validate(raw)

    error: ConfigurationError = exc_info.value
    assert "reranker_top_k" in error.parameter, (
        f"Expected 'reranker_top_k' in error.parameter, got {error.parameter!r} "
        f"for invalid value {invalid_top_k}"
    )
