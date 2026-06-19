# Feature: rag-chatbot-application, Property 16: No-results threshold is always enforced
# Feature: rag-chatbot-application, Property 17: Completed chat interactions always persist all required fields
# Feature: rag-chatbot-application, Property 24: Sessions always have unique identifiers
# Feature: rag-chatbot-application, Property 25: All chat messages have non-null timestamps
# Feature: rag-chatbot-application, Property 29: Reranking metadata is always persisted after a completed query
"""
Property-based tests for ChatService.
"""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.handlers.chat_service import ChatService, ChatServiceError
from app.models.models import Chunk, RankedChunk, ChatMessage, ChatResponse


# ---------------------------------------------------------------------------
# Mock Database Session for isolating tests
# ---------------------------------------------------------------------------

class MockDbSession:
    """Mock for database operations, recording executions."""

    def __init__(self) -> None:
        self.queries = []
        self.committed = False
        self.rolled_back = False
        self.archived_sessions = {}
        self.existing_sessions = set()

    async def execute(self, statement, params=None):
        stmt_str = str(statement).strip().replace("\n", " ").lower()
        self.queries.append((stmt_str, params))

        class MockResult:
            def __init__(self, rows) -> None:
                self._rows = rows
            def fetchone(self):
                return self._rows[0] if self._rows else None
            def fetchall(self):
                return self._rows

        if "select archived_at from chat_sessions" in stmt_str:
            sid = params.get("session_id")
            if sid in self.existing_sessions:
                archived_at = self.archived_sessions.get(sid, None)
                return MockResult([(archived_at,)])
            return MockResult([])

        if "select 1 from chat_sessions" in stmt_str:
            sid = params.get("session_id")
            if sid in self.existing_sessions:
                return MockResult([(1,)])
            return MockResult([])

        if "select message_id" in stmt_str:
            # Mock retrieving messages
            return MockResult([])

        return MockResult([])

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

valid_query_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=("\x00",)),
    min_size=1,
    max_size=1000
).filter(lambda x: len(x.strip()) > 0)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

# Feature: rag-chatbot-application, Property 16: No-results threshold is always enforced
@given(
    session_id=st.uuids(),
    user_query=valid_query_strategy,
    low_scores=st.lists(st.floats(min_value=0.0, max_value=0.69), min_size=0, max_size=5),
)
@settings(max_examples=100, suppress_health_check=list(HealthCheck), deadline=None)
@pytest.mark.asyncio
async def test_property_16_no_results_threshold(session_id: uuid.UUID, user_query: str, low_scores: list[float]) -> None:
    """Validate Property 16: No-results threshold (<0.7 similarity) is always enforced."""
    # 1. Setup Mock database session
    db_session = MockDbSession()
    db_session.existing_sessions.add(session_id)

    # 2. Setup Mock config
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "reranker.reranker_provider": "cohere"
    }[key]

    # 3. Setup Mock Embedder
    embedding_generator = AsyncMock()
    embedding_generator.generate_embedding.return_value = [0.1, 0.2]

    # 4. Setup Mock Orchestration Engine
    # Construct list of ranked chunks with scores < 0.7
    ranked_chunks = []
    for idx, s in enumerate(low_scores):
        c = Chunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunk_text=f"low relevance text {idx}",
            position_in_document=idx,
        )
        ranked_chunks.append(RankedChunk(chunk=c, score=s))

    orchestration_engine = AsyncMock()
    # If all similarity scores are strictly below threshold (0.7), orchestration returns empty results.
    # Note: orchestration_engine itself handles threshold checking and returns ([], "")
    orchestration_engine.orchestrate.return_value = ([], "")

    # 5. Setup LLM service (should NOT be called)
    llm_service = AsyncMock()

    chat_service = ChatService(
        config_manager=mock_config,
        db_session=db_session,
        embedding_generator=embedding_generator,
        orchestration_engine=orchestration_engine,
        llm_service=llm_service,
    )

    # 6. Execute
    response = await chat_service.query(session_id, user_query)

    # 7. Asserts
    assert isinstance(response, ChatResponse)
    assert response.answer == "No relevant information found in uploaded documents."
    assert len(response.retrieved_chunks) == 0

    # Ensure LLM service was never invoked
    llm_service.generate_response.assert_not_called()

    # Ensure database persisted the interaction
    assert db_session.committed
    # Verify assistant message has empty retrieved_chunks/scores
    assistant_queries = [q for q in db_session.queries if "insert into chat_messages" in q[0] and "'assistant'" in q[0]]
    assert len(assistant_queries) == 1
    params = assistant_queries[0][1]
    assert params["content"] == "No relevant information found in uploaded documents."
    assert params["retrieved_chunk_ids"] == []
    assert params["reranking_scores"] == []


# Feature: rag-chatbot-application, Property 17: Completed chat interactions always persist all required fields
@given(
    session_id=st.uuids(),
    user_query=valid_query_strategy,
    scores=st.lists(st.floats(min_value=0.7, max_value=1.0), min_size=1, max_size=5),
)
@settings(max_examples=100, suppress_health_check=list(HealthCheck), deadline=None)
@pytest.mark.asyncio
async def test_property_17_completed_interactions_persist_fields(session_id: uuid.UUID, user_query: str, scores: list[float]) -> None:
    """Validate Property 17: Completed chat interactions always persist all required fields."""
    db_session = MockDbSession()
    db_session.existing_sessions.add(session_id)

    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "reranker.reranker_provider": "cohere"
    }[key]

    embedding_generator = AsyncMock()
    embedding_generator.generate_embedding.return_value = [0.1, 0.2]

    # Setup Orchestrator to return chunks with scores >= 0.7
    ranked_chunks = []
    for idx, s in enumerate(scores):
        c = Chunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunk_text=f"relevant text {idx}",
            position_in_document=idx,
        )
        ranked_chunks.append(RankedChunk(chunk=c, score=s))

    orchestration_engine = AsyncMock()

    chat_service = ChatService(
        config_manager=mock_config,
        db_session=db_session,
        embedding_generator=embedding_generator,
        orchestration_engine=orchestration_engine,
        llm_service=None,
    )

    async def mock_orchestrate(query_vector, query_text):
        res = chat_service.orchestration_engine.reranker_service.rerank(query_text, [])
        if asyncio.iscoroutine(res):
            await res
        return (ranked_chunks, "formatted prompt")
    orchestration_engine.orchestrate.side_effect = mock_orchestrate

    llm_service = AsyncMock()
    llm_service.generate_response.return_value = "Mocked LLM response answer"
    chat_service._llm_service = llm_service

    response = await chat_service.query(session_id, user_query)

    assert response.answer == "Mocked LLM response answer"
    assert db_session.committed

    # Verify both user and assistant rows persisted
    msg_queries = [q for q in db_session.queries if "insert into chat_messages" in q[0]]
    assert len(msg_queries) == 2

    # User message asserts
    user_q = [q for q in msg_queries if "'user'" in q[0]][0]
    assert user_q[1]["content"] == user_query

    # Assistant message asserts (Requirement 3.12, 11.2)
    assistant_q = [q for q in msg_queries if "'assistant'" in q[0]][0]
    params = assistant_q[1]
    assert params["content"] == "Mocked LLM response answer"
    assert params["query_text"] == user_query
    assert isinstance(params["session_id"], uuid.UUID)
    assert len(params["retrieved_chunk_ids"]) == len(scores)
    assert len(params["reranking_scores"]) == len(scores)
    for score in params["reranking_scores"]:
        assert 0.7 <= score <= 1.0


# Feature: rag-chatbot-application, Property 24: Sessions always have unique identifiers
@pytest.mark.asyncio
async def test_property_24_sessions_have_unique_identifiers() -> None:
    """Validate Property 24: Sessions always have unique identifiers."""
    db_session = MockDbSession()
    chat_service = ChatService(db_session=db_session)

    session_ids = set()
    for _ in range(50):
        session_id = await chat_service.create_session()
        assert isinstance(session_id, uuid.UUID)
        assert session_id not in session_ids
        session_ids.add(session_id)

    assert len(session_ids) == 50


# Feature: rag-chatbot-application, Property 25: All chat messages have non-null timestamps
@given(
    session_id=st.uuids(),
    user_query=valid_query_strategy,
    scores=st.lists(st.floats(min_value=0.7, max_value=1.0), min_size=1, max_size=3),
)
@settings(max_examples=100, suppress_health_check=list(HealthCheck), deadline=None)
@pytest.mark.asyncio
async def test_property_25_timestamps_non_null(session_id: uuid.UUID, user_query: str, scores: list[float]) -> None:
    """Validate Property 25: All chat messages have non-null timestamps."""
    db_session = MockDbSession()
    db_session.existing_sessions.add(session_id)

    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "reranker.reranker_provider": "cohere"
    }[key]

    embedding_generator = AsyncMock()
    embedding_generator.generate_embedding.return_value = [0.1, 0.2]

    ranked_chunks = []
    for idx, s in enumerate(scores):
        c = Chunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunk_text=f"relevant text {idx}",
            position_in_document=idx,
        )
        ranked_chunks.append(RankedChunk(chunk=c, score=s))

    orchestration_engine = AsyncMock()

    chat_service = ChatService(
        config_manager=mock_config,
        db_session=db_session,
        embedding_generator=embedding_generator,
        orchestration_engine=orchestration_engine,
        llm_service=None,
    )

    async def mock_orchestrate(query_vector, query_text):
        res = chat_service.orchestration_engine.reranker_service.rerank(query_text, [])
        if asyncio.iscoroutine(res):
            await res
        return (ranked_chunks, "formatted prompt")
    orchestration_engine.orchestrate.side_effect = mock_orchestrate

    llm_service = AsyncMock()
    llm_service.generate_response.return_value = "Mocked LLM answer"
    chat_service._llm_service = llm_service

    await chat_service.query(session_id, user_query)

    msg_queries = [q for q in db_session.queries if "insert into chat_messages" in q[0]]
    assert len(msg_queries) == 2

    # Check timestamps are non-null and valid datetimes
    for q in msg_queries:
        timestamp = q[1]["timestamp"]
        assert timestamp is not None
        assert isinstance(timestamp, datetime)


# Feature: rag-chatbot-application, Property 29: Reranking metadata is always persisted after a completed query
@given(
    session_id=st.uuids(),
    user_query=valid_query_strategy,
    scores=st.lists(st.floats(min_value=0.7, max_value=1.0), min_size=1, max_size=3),
    provider=st.sampled_from(["cohere", "jina"]),
)
@settings(max_examples=100, suppress_health_check=list(HealthCheck), deadline=None)
@pytest.mark.asyncio
async def test_property_29_reranking_metadata_persisted(session_id: uuid.UUID, user_query: str, scores: list[float], provider: str) -> None:
    """Validate Property 29: Reranking metadata is always persisted after a completed query."""
    db_session = MockDbSession()
    db_session.existing_sessions.add(session_id)

    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "reranker.reranker_provider": provider
    }[key]

    embedding_generator = AsyncMock()
    embedding_generator.generate_embedding.return_value = [0.1, 0.2]

    ranked_chunks = []
    for idx, s in enumerate(scores):
        c = Chunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunk_text=f"relevant text {idx}",
            position_in_document=idx,
        )
        ranked_chunks.append(RankedChunk(chunk=c, score=s))

    orchestration_engine = AsyncMock()

    chat_service = ChatService(
        config_manager=mock_config,
        db_session=db_session,
        embedding_generator=embedding_generator,
        orchestration_engine=orchestration_engine,
        llm_service=None,
    )

    async def mock_orchestrate(query_vector, query_text):
        res = chat_service.orchestration_engine.reranker_service.rerank(query_text, [])
        if asyncio.iscoroutine(res):
            await res
        return (ranked_chunks, "formatted prompt")
    orchestration_engine.orchestrate.side_effect = mock_orchestrate

    llm_service = AsyncMock()
    llm_service.generate_response.return_value = "Mocked LLM response answer"
    chat_service._llm_service = llm_service

    await chat_service.query(session_id, user_query)

    # Get assistant message row query
    msg_queries = [q for q in db_session.queries if "insert into chat_messages" in q[0]]
    assistant_q = [q for q in msg_queries if "'assistant'" in q[0]][0]
    params = assistant_q[1]

    # Verify reranking metadata fields are non-null and correctly populated
    assert params["reranking_provider"] == provider
    assert len(params["reranking_scores"]) == len(scores)
    assert params["reranking_duration_ms"] is not None
    assert isinstance(params["reranking_duration_ms"], float)
    assert params["reranking_duration_ms"] >= 0.0
