# Feature: rag-chatbot-application, Property 26: Reranked chunks are always sorted by descending reranking score
# Feature: rag-chatbot-application, Property 28: Reranking scores are always in [0.0, 1.0]
"""
Property-based and unit tests for RerankerService.

Validates: Requirements 13.1–13.6, 13.8–13.9
"""

import time
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.handlers.reranker_service import RerankerService, RerankerError
from app.models.models import Chunk, RankedChunk, AppConfig


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

chunk_strategy = st.builds(
    Chunk,
    chunk_id=st.uuids(),
    document_id=st.uuids(),
    chunk_text=st.text(min_size=1, max_size=200),
    position_in_document=st.integers(min_value=0, max_value=100),
    contextual_summary=st.text(min_size=0, max_size=100),
    token_count=st.integers(min_value=1, max_value=500),
)


class MockCohereResult:
    def __init__(self, index: int, relevance_score: float) -> None:
        self.index = index
        self.relevance_score = relevance_score


class MockCohereResponse:
    def __init__(self, results: list) -> None:
        self.results = results


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

# Feature: rag-chatbot-application, Property 26: Reranked chunks are always sorted by descending reranking score
# Feature: rag-chatbot-application, Property 28: Reranking scores are always in [0.0, 1.0]
@given(
    query=st.text(min_size=1, max_size=50),
    chunks=st.lists(chunk_strategy, min_size=1, max_size=15),
    # Generate scores that can be outside [0.0, 1.0] to test clamping
    scores=st.lists(st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False), min_size=15, max_size=15),
    provider=st.sampled_from(["cohere", "jina"]),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_reranker_properties(query: str, chunks: list[Chunk], scores: list[float], provider: str) -> None:
    """Validate Property 26 (sorting descending) and Property 28 (scores in [0.0, 1.0])."""
    # 1. Setup Mock Configuration
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "reranker.reranker_provider": provider,
        "reranker.reranker_model_name": "test-model",
        "reranker.reranker_top_k": len(chunks),
    }[key]

    # Align number of scores to match number of chunks
    run_scores = scores[:len(chunks)]

    # 2. Setup Provider Mock Client
    cohere_client = MagicMock()
    httpx_client = MagicMock()

    if provider == "cohere":
        # Mock Cohere response
        cohere_results = [MockCohereResult(i, s) for i, s in enumerate(run_scores)]
        cohere_client.rerank.return_value = MockCohereResponse(cohere_results)
    else:
        # Mock Jina response
        jina_results = [{"index": i, "relevance_score": s} for i, s in enumerate(run_scores)]
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": jina_results}
        mock_response.status_code = 200
        httpx_client.post.return_value = mock_response

    # 3. Invoke Service
    service = RerankerService(
        config_manager=mock_config,
        cohere_client=cohere_client,
        httpx_client=httpx_client,
    )
    ranked_result = service.rerank(query, chunks)

    # 4. Assertions
    assert len(ranked_result) == len(chunks)

    # Assert P28: Reranking scores are always in [0.0, 1.0]
    for rc in ranked_result:
        assert 0.0 <= rc.score <= 1.0, f"Score {rc.score} is not within [0.0, 1.0]"

    # Assert P26: Reranked chunks are always sorted by descending reranking score
    for idx in range(len(ranked_result) - 1):
        assert ranked_result[idx].score >= ranked_result[idx + 1].score, (
            f"Result list is not sorted by descending score: "
            f"{[rc.score for rc in ranked_result]}"
        )


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

def test_unit_provider_selection() -> None:
    """Verify that provider selection at startup switchable via config without code changes.

    Validates: Requirements 13.3, 13.6
    """
    mock_config = MagicMock()
    import uuid
    chunks = [
        Chunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunk_text="test chunk",
            position_in_document=0,
        )
    ]

    # Test Case 1: Cohere active
    mock_config.get.side_effect = lambda key: {
        "reranker.reranker_provider": "cohere",
        "reranker.reranker_model_name": "cohere-model",
        "reranker.reranker_top_k": 5,
    }[key]
    cohere_client = MagicMock()
    cohere_client.rerank.return_value = MockCohereResponse([MockCohereResult(0, 0.85)])
    httpx_client = MagicMock()

    service = RerankerService(
        config_manager=mock_config,
        cohere_client=cohere_client,
        httpx_client=httpx_client,
    )
    res_cohere = service.rerank("query", chunks)
    assert len(res_cohere) == 1
    cohere_client.rerank.assert_called_once()
    httpx_client.post.assert_not_called()

    # Test Case 2: Jina active
    mock_config.get.side_effect = lambda key: {
        "reranker.reranker_provider": "jina",
        "reranker.reranker_model_name": "jina-model",
        "reranker.reranker_top_k": 5,
    }[key]
    cohere_client = MagicMock()
    httpx_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": [{"index": 0, "relevance_score": 0.9}]}
    mock_response.status_code = 200
    httpx_client.post.return_value = mock_response

    service = RerankerService(
        config_manager=mock_config,
        cohere_client=cohere_client,
        httpx_client=httpx_client,
    )
    res_jina = service.rerank("query", chunks)
    assert len(res_jina) == 1
    httpx_client.post.assert_called_once()
    cohere_client.rerank.assert_not_called()


def test_unit_rerank_duration_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that a warning is logged when reranking duration exceeds 50 ms.

    Validates: Requirement 13.4
    """
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "reranker.reranker_provider": "cohere",
        "reranker.reranker_model_name": "cohere-model",
        "reranker.reranker_top_k": 5,
    }[key]
    
    cohere_client = MagicMock()
    
    # Simulate API call taking 60 ms
    def slow_rerank(*args, **kwargs):
        time.sleep(0.060)
        return MockCohereResponse([MockCohereResult(0, 0.85)])
        
    cohere_client.rerank.side_effect = slow_rerank
    httpx_client = MagicMock()

    service = RerankerService(
        config_manager=mock_config,
        cohere_client=cohere_client,
        httpx_client=httpx_client,
    )
    import uuid
    chunks = [
        Chunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunk_text="test chunk",
            position_in_document=0,
        )
    ]
    
    # We should run this and check logs
    import logging
    with caplog.at_level(logging.WARNING):
        service.rerank("query", chunks)
        
    warning_logs = [record.message for record in caplog.records if record.levelname == "WARNING"]
    assert any("exceeded 50 ms" in log or "reranking took" in log for log in warning_logs), (
        f"Expected performance warning log, got: {warning_logs}"
    )
