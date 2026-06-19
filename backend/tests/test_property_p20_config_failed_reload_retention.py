# Feature: rag-chatbot-application, Property 20: Failed configuration reload retains the previous valid configuration
"""
Property-based tests for P20: Failed configuration reload retains the previous valid configuration.

**Validates: Requirement 5.11**

For any reload attempt that results in a validation failure, the active configuration
immediately after the failed reload must be identical to the active configuration
immediately before the reload attempt. The system must continue operating on the
previous valid settings.
"""
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.app.config.configuration_manager import ConfigurationError, ConfigurationManager
from backend.app.models.models import AppConfig


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


def _configs_equal(a: AppConfig, b: AppConfig) -> bool:
    """Compare two AppConfig objects field-by-field for equality."""
    return a.model_dump() == b.model_dump()


def _get_config_value(cm: ConfigurationManager, key: str) -> Any:
    """Get a config value using dot-notation."""
    return cm.get(key)


# ---------------------------------------------------------------------------
# P20 – Property tests
# ---------------------------------------------------------------------------


# Feature: rag-chatbot-application, Property 20: Failed configuration reload retains the previous valid configuration
@given(
    invalid_chunk_size=st.integers().filter(lambda x: x < 300 or x > 500)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p20_reload_failure_retains_previous_config_chunk_size(
    invalid_chunk_size: int,
) -> None:
    """P20: A reload attempt with invalid chunk_size_tokens must retain the previous valid config.

    **Validates: Requirement 5.11**

    For any valid configuration that has been loaded, if a subsequent reload attempt
    fails validation due to an out-of-range chunk_size_tokens value, the active
    configuration immediately after the reload must be identical to the configuration
    before the reload attempt.
    """
    valid_raw = _valid_raw_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Step 1: Write valid config and load it
        config_file = Path(tmp_dir) / "config.yaml"
        config_file.write_text(
            json.dumps(valid_raw),
            encoding="utf-8",
        )

        cm = ConfigurationManager(tmp_dir)
        original_config = cm.load()

        # Step 2: Store the original config value we'll check
        original_chunk_size = _get_config_value(cm, "chunking.chunk_size_tokens")

        # Step 3: Modify the config file to have invalid chunk_size_tokens
        invalid_raw = valid_raw.copy()
        invalid_raw["chunking"] = valid_raw["chunking"].copy()
        invalid_raw["chunking"]["chunk_size_tokens"] = invalid_chunk_size
        config_file.write_text(
            json.dumps(invalid_raw),
            encoding="utf-8",
        )

        # Step 4: Attempt reload - this should fail validation
        result = cm.reload()

        # Step 5: Verify reload failed
        assert result.success is False, (
            f"Expected reload to fail for invalid chunk_size_tokens={invalid_chunk_size}, "
            f"but it succeeded with config={result.config}"
        )

        # Step 6: Verify the active configuration is unchanged
        # The key: use get() on the SAME ConfigurationManager instance
        current_chunk_size = _get_config_value(cm, "chunking.chunk_size_tokens")

        assert current_chunk_size == original_chunk_size, (
            f"Config value changed after failed reload! "
            f"Original: {original_chunk_size}, Current: {current_chunk_size}"
        )


# Feature: rag-chatbot-application, Property 20: Failed configuration reload retains the previous valid configuration
@given(
    invalid_overlap=st.floats(allow_nan=False, allow_infinity=False).filter(
        lambda x: x < 10.0 or x > 15.0
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p20_reload_failure_retains_previous_config_overlap(
    invalid_overlap: float,
) -> None:
    """P20: A reload attempt with invalid overlap_percentage must retain the previous valid config.

    **Validates: Requirement 5.11**

    For any valid configuration that has been loaded, if a subsequent reload attempt
    fails validation due to an out-of-range overlap_percentage value, the active
    configuration immediately after the reload must be identical to the configuration
    before the reload attempt.
    """
    valid_raw = _valid_raw_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Step 1: Write valid config and load it
        config_file = Path(tmp_dir) / "config.yaml"
        config_file.write_text(
            json.dumps(valid_raw),
            encoding="utf-8",
        )

        cm = ConfigurationManager(tmp_dir)
        original_config = cm.load()

        # Step 2: Store the original config value we'll check
        original_overlap = _get_config_value(cm, "chunking.overlap_percentage")

        # Step 3: Modify the config file to have invalid overlap_percentage
        invalid_raw = valid_raw.copy()
        invalid_raw["chunking"] = valid_raw["chunking"].copy()
        invalid_raw["chunking"]["overlap_percentage"] = invalid_overlap
        config_file.write_text(
            json.dumps(invalid_raw),
            encoding="utf-8",
        )

        # Step 4: Attempt reload - this should fail validation
        result = cm.reload()

        # Step 5: Verify reload failed
        assert result.success is False, (
            f"Expected reload to fail for invalid overlap_percentage={invalid_overlap}, "
            f"but it succeeded with config={result.config}"
        )

        # Step 6: Verify the active configuration is unchanged
        current_overlap = _get_config_value(cm, "chunking.overlap_percentage")

        assert current_overlap == original_overlap, (
            f"Config value changed after failed reload! "
            f"Original: {original_overlap}, Current: {current_overlap}"
        )


# Feature: rag-chatbot-application, Property 20: Failed configuration reload retains the previous valid configuration
@given(
    invalid_top_k=st.integers().filter(lambda x: x < 1 or x > 20)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p20_reload_failure_retains_previous_config_top_k(
    invalid_top_k: int,
) -> None:
    """P20: A reload attempt with invalid reranker_top_k must retain the previous valid config.

    **Validates: Requirement 5.11**

    For any valid configuration that has been loaded, if a subsequent reload attempt
    fails validation due to an out-of-range reranker_top_k value, the active
    configuration immediately after the reload must be identical to the configuration
    before the reload attempt.
    """
    valid_raw = _valid_raw_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Step 1: Write valid config and load it
        config_file = Path(tmp_dir) / "config.yaml"
        config_file.write_text(
            json.dumps(valid_raw),
            encoding="utf-8",
        )

        cm = ConfigurationManager(tmp_dir)
        original_config = cm.load()

        # Step 2: Store the original config value we'll check
        original_top_k = _get_config_value(cm, "reranker.reranker_top_k")

        # Step 3: Modify the config file to have invalid reranker_top_k
        invalid_raw = valid_raw.copy()
        invalid_raw["reranker"] = valid_raw["reranker"].copy()
        invalid_raw["reranker"]["reranker_top_k"] = invalid_top_k
        config_file.write_text(
            json.dumps(invalid_raw),
            encoding="utf-8",
        )

        # Step 4: Attempt reload - this should fail validation
        result = cm.reload()

        # Step 5: Verify reload failed
        assert result.success is False, (
            f"Expected reload to fail for invalid reranker_top_k={invalid_top_k}, "
            f"but it succeeded with config={result.config}"
        )

        # Step 6: Verify the active configuration is unchanged
        current_top_k = _get_config_value(cm, "reranker.reranker_top_k")

        assert current_top_k == original_top_k, (
            f"Config value changed after failed reload! "
            f"Original: {original_top_k}, Current: {current_top_k}"
        )