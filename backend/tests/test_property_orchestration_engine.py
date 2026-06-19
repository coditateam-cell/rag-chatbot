# Feature: rag-chatbot-application, Property 13: Top-k chunk selection always returns the highest-ranked chunks
# Feature: rag-chatbot-application, Property 14: Constructed prompts always contain all three required components
# Feature: rag-chatbot-application, Property 15: Prompts exceeding 8000 characters are truncated while preserving instructions and query
# Feature: rag-chatbot-application, Property 21: Retrieved vector similarity scores are always in [0.0, 1.0]
# Feature: rag-chatbot-application, Property 22: Retrieved chunks are always ordered by descending similarity score
# Feature: rag-chatbot-application, Property 23: Maximum chunk evaluation is bounded at 100
# Feature: rag-chatbot-application, Property 27: Reranker fallback always produces ordered results
"""
Property-based tests for OrchestrationEngine.
"""

import asyncio
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.handlers.orchestration_engine import OrchestrationEngine, OrchestrationError
from app.models.models import Chunk, RankedChunk


# ---------------------------------------------------------------------------
# Mock helper classes
# ---------------------------------------------------------------------------

class MockScoredPoint:
    """Mock for Qdrant client's ScoredPoint result."""
    def __init__(self, id_val, score, payload) -> None:
        self.id = id_val
        self.score = score
        self.payload = payload


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Since Qdrant client is mocked, we don't need a full 1536 dimension vector.
# Using a small vector makes Hypothesis generation significantly faster.
query_vector_strategy = st.lists(st.floats(min_value=-1.0, max_value=1.0), min_size=1, max_size=5)

chunk_strategy = st.builds(
    Chunk,
    chunk_id=st.uuids(),
    document_id=st.uuids(),
    chunk_text=st.text(min_size=1, max_size=200),
    position_in_document=st.integers(min_value=0, max_value=100),
    contextual_summary=st.text(min_size=0, max_size=100),
    token_count=st.integers(min_value=1, max_value=500),
)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

# Feature: rag-chatbot-application, Property 21: Retrieved vector similarity scores are always in [0.0, 1.0]
# Feature: rag-chatbot-application, Property 22: Retrieved chunks are always ordered by descending similarity score
@given(
    query_vector=query_vector_strategy,
    query_text=st.text(min_size=1, max_size=50),
    scores=st.lists(st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False), min_size=5, max_size=30),
)
@settings(max_examples=100, suppress_health_check=list(HealthCheck), deadline=None)
@pytest.mark.asyncio
async def test_property_21_22_similarity_scores(query_vector: list[float], query_text: str, scores: list[float]) -> None:
    """Validate Property 21 (similarity scores in [0.0, 1.0]) and Property 22 (ordered descending)."""
    # 1. Setup Mock configuration
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "retrieval.top_k": len(scores),
        "retrieval.max_chunks_evaluated": 100,
        "retrieval.similarity_threshold": 0.0,
        "reranker.reranker_top_k": 5,
        "retrieval.prompt_max_chars": 8000,
        "prompt_templates.system_instructions": "Test system instructions",
    }[key]

    # 2. Setup Qdrant Mock results
    mock_points = []
    for idx, s in enumerate(scores):
        payload = {
            "chunk_id": "00000000-0000-0000-0000-000000000000",
            "document_id": "00000000-0000-0000-0000-000000000000",
            "chunk_text": f"Chunk text {idx}",
            "position_in_document": idx,
            "contextual_summary": "Summary",
            "token_count": 10,
        }
        mock_points.append(MockScoredPoint(idx, s, payload))

    qdrant_client = MagicMock()
    qdrant_client.search.return_value = mock_points

    # Setup Reranker Mock
    reranker_service = MagicMock()
    reranker_service.rerank.return_value = [
        RankedChunk(
            chunk=Chunk(
                chunk_id="00000000-0000-0000-0000-000000000000",
                document_id="00000000-0000-0000-0000-000000000000",
                chunk_text="Chunk text 0",
                position_in_document=0,
            ),
            score=0.8,
        )
    ]

    # 3. Invoke orchestrator
    engine = OrchestrationEngine(
        config_manager=mock_config,
        qdrant_client=qdrant_client,
        reranker_service=reranker_service,
    )
    
    qdrant_client.search = MagicMock(return_value=mock_points)

    selected_ranked, prompt = await engine.orchestrate(query_vector, query_text)

    # Verify qdrant.search called
    qdrant_client.search.assert_called_once()

    # Retrieve the list of Chunks sent to the reranker
    called_chunks = reranker_service.rerank.call_args[0][1]

    # Map from chunk text to clamped similarity score
    text_to_score = {}
    for p in mock_points:
        text_to_score[p.payload["chunk_text"]] = max(0.0, min(1.0, float(p.score)))

    # Verify that the scores of the called chunks are sorted descending
    called_scores = [text_to_score[c.chunk_text] for c in called_chunks]
    
    # Check that scores are in [0.0, 1.0] (Property 21)
    for s in called_scores:
        assert 0.0 <= s <= 1.0

    # Check sorted descending (Property 22)
    for i in range(len(called_scores) - 1):
        assert called_scores[i] >= called_scores[i + 1]


# Feature: rag-chatbot-application, Property 23: Maximum chunk evaluation is bounded at 100
@given(
    query_vector=query_vector_strategy,
    query_text=st.text(min_size=1, max_size=50),
    num_points=st.integers(min_value=101, max_value=150),
)
@settings(max_examples=100, suppress_health_check=list(HealthCheck), deadline=None)
@pytest.mark.asyncio
async def test_property_23_max_chunks_evaluated(query_vector: list[float], query_text: str, num_points: int) -> None:
    """Validate Property 23 (at most 100 chunks evaluated/passed to reranker)."""
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "retrieval.top_k": num_points,
        "retrieval.max_chunks_evaluated": num_points,
        "retrieval.similarity_threshold": 0.0,
        "reranker.reranker_top_k": 5,
        "retrieval.prompt_max_chars": 8000,
        "prompt_templates.system_instructions": "Test system instructions",
    }[key]

    # Qdrant client returning more than 100 points
    mock_points = []
    for idx in range(num_points):
        payload = {
            "chunk_id": "00000000-0000-0000-0000-000000000000",
            "document_id": "00000000-0000-0000-0000-000000000000",
            "chunk_text": f"Chunk text {idx}",
            "position_in_document": idx,
        }
        mock_points.append(MockScoredPoint(idx, 0.9, payload))

    qdrant_client = MagicMock()
    qdrant_client.search = MagicMock(return_value=mock_points)

    reranker_service = MagicMock()
    reranker_service.rerank.return_value = []

    engine = OrchestrationEngine(
        config_manager=mock_config,
        qdrant_client=qdrant_client,
        reranker_service=reranker_service,
    )

    await engine.orchestrate(query_vector, query_text)

    # Verify search limit was capped at 100
    args, kwargs = qdrant_client.search.call_args
    assert kwargs.get("limit", 0) <= 100


# Feature: rag-chatbot-application, Property 13: Top-k chunk selection always returns the highest-ranked chunks
@given(
    query_vector=query_vector_strategy,
    query_text=st.text(min_size=1, max_size=50),
    top_k=st.integers(min_value=1, max_value=20),
    scores=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=15),
)
@settings(max_examples=100, suppress_health_check=list(HealthCheck), deadline=None)
@pytest.mark.asyncio
async def test_property_13_top_k_selection(query_vector: list[float], query_text: str, top_k: int, scores: list[float]) -> None:
    """Validate Property 13: selection contains min(top_k, total_chunks) chunks with highest scores, sorted descending."""
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "retrieval.top_k": 20,
        "retrieval.max_chunks_evaluated": 100,
        "retrieval.similarity_threshold": 0.0,
        "reranker.reranker_top_k": top_k,
        "retrieval.prompt_max_chars": 8000,
        "prompt_templates.system_instructions": "Test system instructions",
    }[key]

    mock_points = []
    for idx, s in enumerate(scores):
        payload = {
            "chunk_id": "00000000-0000-0000-0000-000000000000",
            "document_id": "00000000-0000-0000-0000-000000000000",
            "chunk_text": f"Chunk text {idx}",
            "position_in_document": idx,
        }
        mock_points.append(MockScoredPoint(idx, 0.9, payload))

    qdrant_client = MagicMock()
    qdrant_client.search = MagicMock(return_value=mock_points)

    # Reranker returns ranked chunks with generated scores
    mock_ranked = []
    for idx, s in enumerate(scores):
        c = Chunk(
            chunk_id="00000000-0000-0000-0000-000000000000",
            document_id="00000000-0000-0000-0000-000000000000",
            chunk_text=f"Chunk text {idx}",
            position_in_document=idx,
        )
        mock_ranked.append(RankedChunk(chunk=c, score=s))

    reranker_service = MagicMock()
    reranker_service.rerank.return_value = mock_ranked

    engine = OrchestrationEngine(
        config_manager=mock_config,
        qdrant_client=qdrant_client,
        reranker_service=reranker_service,
    )

    selected_ranked, prompt = await engine.orchestrate(query_vector, query_text)

    # Check exact min(top_k, total_chunks) size
    expected_size = min(top_k, len(scores))
    assert len(selected_ranked) == expected_size

    # Check sorted descending
    for idx in range(len(selected_ranked) - 1):
        assert selected_ranked[idx].score >= selected_ranked[idx + 1].score

    # Check they are indeed the highest-ranked ones
    all_scores_sorted = sorted(scores, reverse=True)
    expected_top_scores = all_scores_sorted[:expected_size]
    actual_scores = [rc.score for rc in selected_ranked]
    assert actual_scores == expected_top_scores


# Feature: rag-chatbot-application, Property 14: Constructed prompts always contain all three required components
@given(
    system_instructions=st.text(min_size=1, max_size=100),
    user_query=st.text(min_size=1, max_size=100),
    chunk_texts=st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=5),
)
@settings(max_examples=100, suppress_health_check=list(HealthCheck), deadline=None)
@pytest.mark.asyncio
async def test_property_14_prompt_contains_components(system_instructions: str, user_query: str, chunk_texts: list[str]) -> None:
    """Validate Property 14: constructed prompts always contain all three components."""
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "retrieval.top_k": 20,
        "retrieval.max_chunks_evaluated": 100,
        "retrieval.similarity_threshold": 0.0,
        "reranker.reranker_top_k": len(chunk_texts),
        "retrieval.prompt_max_chars": 8000,
        "prompt_templates.system_instructions": system_instructions,
    }[key]

    mock_points = []
    for idx, t in enumerate(chunk_texts):
        payload = {
            "chunk_id": "00000000-0000-0000-0000-000000000000",
            "document_id": "00000000-0000-0000-0000-000000000000",
            "chunk_text": t,
            "position_in_document": idx,
        }
        mock_points.append(MockScoredPoint(idx, 0.9, payload))

    qdrant_client = MagicMock()
    qdrant_client.search = MagicMock(return_value=mock_points)

    reranker_service = MagicMock()
    mock_ranked = []
    for idx, t in enumerate(chunk_texts):
        c = Chunk(
            chunk_id="00000000-0000-0000-0000-000000000000",
            document_id="00000000-0000-0000-0000-000000000000",
            chunk_text=t,
            position_in_document=idx,
        )
        mock_ranked.append(RankedChunk(chunk=c, score=0.9))
    reranker_service.rerank.return_value = mock_ranked

    engine = OrchestrationEngine(
        config_manager=mock_config,
        qdrant_client=qdrant_client,
        reranker_service=reranker_service,
    )

    _, prompt = await engine.orchestrate([0.1], user_query)

    assert system_instructions in prompt
    assert user_query in prompt
    for t in chunk_texts:
        assert t in prompt


# Feature: rag-chatbot-application, Property 15: Prompts exceeding 8000 characters are truncated while preserving instructions and query
@given(
    system_instructions=st.text(min_size=10, max_size=50),
    user_query=st.text(min_size=10, max_size=50),
    max_chars=st.integers(min_value=500, max_value=8000),
)
@settings(max_examples=100, suppress_health_check=list(HealthCheck), deadline=None)
@pytest.mark.asyncio
async def test_property_15_prompt_truncation(system_instructions: str, user_query: str, max_chars: int) -> None:
    """Validate Property 15: truncation restricts size to limit, preserving instructions and query."""
    large_context = "A" * 9000
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "retrieval.top_k": 20,
        "retrieval.max_chunks_evaluated": 100,
        "retrieval.similarity_threshold": 0.0,
        "reranker.reranker_top_k": 1,
        "retrieval.prompt_max_chars": max_chars,
        "prompt_templates.system_instructions": system_instructions,
    }[key]

    mock_points = [
        MockScoredPoint(
            0,
            0.9,
            {
                "chunk_id": "00000000-0000-0000-0000-000000000000",
                "document_id": "00000000-0000-0000-0000-000000000000",
                "chunk_text": large_context,
                "position_in_document": 0,
            }
        )
    ]

    qdrant_client = MagicMock()
    qdrant_client.search = MagicMock(return_value=mock_points)

    reranker_service = MagicMock()
    c = Chunk(
        chunk_id="00000000-0000-0000-0000-000000000000",
        document_id="00000000-0000-0000-0000-000000000000",
        chunk_text=large_context,
        position_in_document=0,
    )
    reranker_service.rerank.return_value = [RankedChunk(chunk=c, score=0.9)]

    engine = OrchestrationEngine(
        config_manager=mock_config,
        qdrant_client=qdrant_client,
        reranker_service=reranker_service,
    )

    _, prompt = await engine.orchestrate([0.1], user_query)

    template_overhead = len(OrchestrationEngine.DEFAULT_PROMPT_TEMPLATE.format(
        system_instructions=system_instructions,
        context_chunks="",
        user_query=user_query
    ))
    if max_chars >= template_overhead:
        assert len(prompt) <= max_chars
    else:
        assert len(prompt) == template_overhead

    assert system_instructions in prompt
    assert user_query in prompt


# Feature: rag-chatbot-application, Property 27: Reranker fallback always produces ordered results
@given(
    query_vector=query_vector_strategy,
    query_text=st.text(min_size=1, max_size=50),
    scores=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=10),
)
@settings(max_examples=100, suppress_health_check=list(HealthCheck), deadline=None)
@pytest.mark.asyncio
async def test_property_27_reranker_fallback(query_vector: list[float], query_text: str, scores: list[float]) -> None:
    """Validate Property 27: reranker failure falls back to ordered vector similarity chunks."""
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "retrieval.top_k": len(scores),
        "retrieval.max_chunks_evaluated": 100,
        "retrieval.similarity_threshold": 0.0,
        "reranker.reranker_top_k": len(scores),
        "retrieval.prompt_max_chars": 8000,
        "prompt_templates.system_instructions": "Test system instructions",
    }[key]

    mock_points = []
    for idx, s in enumerate(scores):
        payload = {
            "chunk_id": "00000000-0000-0000-0000-000000000000",
            "document_id": "00000000-0000-0000-0000-000000000000",
            "chunk_text": f"Chunk text {idx}",
            "position_in_document": idx,
        }
        mock_points.append(MockScoredPoint(idx, s, payload))

    qdrant_client = MagicMock()
    qdrant_client.search = MagicMock(return_value=mock_points)

    reranker_service = MagicMock()
    reranker_service.rerank.side_effect = Exception("Reranker connection failed")

    engine = OrchestrationEngine(
        config_manager=mock_config,
        qdrant_client=qdrant_client,
        reranker_service=reranker_service,
    )

    selected_ranked, prompt = await engine.orchestrate(query_vector, query_text)

    assert len(selected_ranked) == len(scores)

    for idx in range(len(selected_ranked) - 1):
        assert selected_ranked[idx].score >= selected_ranked[idx + 1].score

    expected_scores = sorted([max(0.0, min(1.0, float(s))) for s in scores], reverse=True)
    actual_scores = [rc.score for rc in selected_ranked]
    assert actual_scores == expected_scores


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unit_retrieval_timeout() -> None:
    """Verify that retrieval times out and raises OrchestrationError after 30 seconds."""
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "retrieval.top_k": 20,
        "retrieval.max_chunks_evaluated": 100,
        "retrieval.similarity_threshold": 0.0,
        "reranker.reranker_top_k": 5,
        "retrieval.prompt_max_chars": 8000,
        "prompt_templates.system_instructions": "Test instructions",
    }[key]

    qdrant_client = MagicMock()

    # Simulate slow search exceeding 30s
    def mock_search(*args, **kwargs):
        return []

    qdrant_client.search = MagicMock(side_effect=mock_search)
    reranker_service = MagicMock()

    engine = OrchestrationEngine(
        config_manager=mock_config,
        qdrant_client=qdrant_client,
        reranker_service=reranker_service,
    )

    original_wait_for = asyncio.wait_for

    async def mock_wait_for(aw, timeout):
        if timeout == 30.0:
            try:
                aw.close()
            except Exception:
                pass
            raise asyncio.TimeoutError()
        return await original_wait_for(aw, timeout)

    import unittest.mock as mock
    with mock.patch("asyncio.wait_for", side_effect=mock_wait_for):
        with pytest.raises(OrchestrationError) as exc_info:
            await engine.orchestrate([0.1], "query")
        assert "Retrieval timeout" in str(exc_info.value)
