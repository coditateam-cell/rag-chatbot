# Feature: rag-chatbot-application, Property 19: Configuration round-trip preserves all values
"""
Property-based tests for P19: Configuration round-trip preserves all values.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.13**

For any valid AppConfig, serialising it to JSON or YAML and reloading it
through ConfigurationManager must produce an equivalent AppConfig — every
field must have the same value after the round-trip.
"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.app.config.configuration_manager import ConfigurationManager
from backend.app.models.models import AppConfig

# ---------------------------------------------------------------------------
# Strategies — generate valid raw config dicts
# ---------------------------------------------------------------------------

# Safe string alphabet: letters, digits, and common model-name punctuation.
_SAFE_TEXT = st.from_regex(r"[a-zA-Z0-9 _\-/\.]+", fullmatch=True)
# Even safer alphabet for system_instructions — printable ASCII but avoid
# characters that can trip up YAML block scalars.
_SAFE_INSTRUCTIONS = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters=" _-./",
    ),
    min_size=1,
    max_size=200,
)


@st.composite
def valid_raw_configs(draw: st.DrawFn) -> dict:
    """Hypothesis strategy that produces a valid raw configuration dict."""
    return {
        "prompt_templates": {
            "system_instructions": draw(_SAFE_INSTRUCTIONS),
        },
        "chunking": {
            "chunk_size_tokens": draw(st.integers(min_value=300, max_value=500)),
            "overlap_percentage": draw(
                st.floats(
                    min_value=10.0,
                    max_value=15.0,
                    allow_nan=False,
                    allow_infinity=False,
                )
            ),
            "enable_contextual_summaries": draw(st.booleans()),
        },
        "models": {
            "llm_model_name": draw(_SAFE_TEXT.filter(lambda s: len(s) >= 1)),
            "embedding_model_name": draw(_SAFE_TEXT.filter(lambda s: len(s) >= 1)),
        },
        "reranker": {
            "reranker_provider": draw(st.sampled_from(["cohere", "jina"])),
            "reranker_model_name": draw(_SAFE_TEXT.filter(lambda s: len(s) >= 1)),
            "reranker_top_k": draw(st.integers(min_value=1, max_value=20)),
        },
        "retrieval": {
            "top_k": draw(st.integers(min_value=1, max_value=50)),
            "similarity_threshold": draw(
                st.floats(
                    min_value=0.0,
                    max_value=1.0,
                    allow_nan=False,
                    allow_infinity=False,
                )
            ),
            "max_chunks_evaluated": draw(st.integers(min_value=1, max_value=10000)),
            "prompt_max_chars": draw(st.integers(min_value=1000, max_value=100000)),
        },
    }


# ---------------------------------------------------------------------------
# Helper: compare two AppConfig objects tolerating float precision drift
# ---------------------------------------------------------------------------


def _configs_equal(a: AppConfig, b: AppConfig) -> bool:
    """Compare two AppConfig objects field-by-field, using pytest.approx for floats."""
    da = a.model_dump()
    db = b.model_dump()
    return _dicts_approx_equal(da, db)


def _dicts_approx_equal(a: dict, b: dict) -> bool:
    if set(a.keys()) != set(b.keys()):
        return False
    for key in a:
        va, vb = a[key], b[key]
        if isinstance(va, dict) and isinstance(vb, dict):
            if not _dicts_approx_equal(va, vb):
                return False
        elif isinstance(va, float) or isinstance(vb, float):
            if va != pytest.approx(vb, rel=1e-6, abs=1e-9):
                return False
        else:
            if va != vb:
                return False
    return True


# ---------------------------------------------------------------------------
# P19 — Property tests
# ---------------------------------------------------------------------------


# Feature: rag-chatbot-application, Property 19: Configuration round-trip preserves all values
@given(raw=valid_raw_configs())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p19_yaml_roundtrip_preserves_all_values(raw: dict) -> None:
    """P19: Serialising a valid config to YAML and reloading via ConfigurationManager
    must produce an AppConfig identical to the original.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.13**
    """
    # Build the original AppConfig from the generated raw dict
    original = ConfigurationManager._validate(raw)

    with tempfile.TemporaryDirectory() as tmp_dir:
        config_file = Path(tmp_dir) / "config.yaml"
        config_file.write_text(
            yaml.dump(raw, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        cm = ConfigurationManager(tmp_dir)
        loaded = cm.load()

    assert _configs_equal(original, loaded), (
        f"YAML round-trip produced a different AppConfig.\n"
        f"Original dump: {original.model_dump()}\n"
        f"Loaded dump:   {loaded.model_dump()}"
    )


# Feature: rag-chatbot-application, Property 19: Configuration round-trip preserves all values
@given(raw=valid_raw_configs())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p19_json_roundtrip_preserves_all_values(raw: dict) -> None:
    """P19: Serialising a valid config to JSON and reloading via ConfigurationManager
    must produce an AppConfig identical to the original.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.13**
    """
    original = ConfigurationManager._validate(raw)

    with tempfile.TemporaryDirectory() as tmp_dir:
        config_file = Path(tmp_dir) / "config.json"
        config_file.write_text(json.dumps(raw), encoding="utf-8")

        cm = ConfigurationManager(tmp_dir)
        loaded = cm.load()

    assert _configs_equal(original, loaded), (
        f"JSON round-trip produced a different AppConfig.\n"
        f"Original dump: {original.model_dump()}\n"
        f"Loaded dump:   {loaded.model_dump()}"
    )


# Feature: rag-chatbot-application, Property 19: Configuration round-trip preserves all values
@given(raw=valid_raw_configs())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p19_roundtrip_via_pydantic_model_dict(raw: dict) -> None:
    """P19: Generating an AppConfig via model_validate, serialising via model_dump to YAML,
    then reloading must produce an equal AppConfig.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.13**
    """
    # Build AppConfig from raw, then use model_dump as the serialisation source
    original = AppConfig.model_validate(raw)
    dumped = original.model_dump()

    with tempfile.TemporaryDirectory() as tmp_dir:
        config_file = Path(tmp_dir) / "config.yaml"
        config_file.write_text(
            yaml.dump(dumped, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        cm = ConfigurationManager(tmp_dir)
        reloaded = cm.load()

    assert _configs_equal(original, reloaded), (
        f"Pydantic model_dump → YAML round-trip produced a different AppConfig.\n"
        f"Original dump: {original.model_dump()}\n"
        f"Reloaded dump: {reloaded.model_dump()}"
    )
