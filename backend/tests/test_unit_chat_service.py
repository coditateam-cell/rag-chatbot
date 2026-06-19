"""
Unit tests for ChatService.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock

import pytest

from app.handlers.chat_service import ChatService, ChatServiceError
from app.handlers.embedding_generator import EmbeddingFailureError
from app.models.models import Chunk, RankedChunk, ChatMessage, ChatResponse


# ---------------------------------------------------------------------------
# In-Memory Mock Database Session for Unit Tests
# ---------------------------------------------------------------------------

class InMemDbSession:
    """Simulates a subset of PostgreSQL operations in-memory for testing."""

    def __init__(self) -> None:
        self.sessions = {}
        self.messages = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement, params=None):
        stmt_str = str(statement).strip().replace("\n", " ").lower()

        class MockResult:
            def __init__(self, rows) -> None:
                self._rows = rows
            def fetchone(self):
                return self._rows[0] if self._rows else None
            def fetchall(self):
                return self._rows

        if "insert into chat_sessions" in stmt_str:
            sid = params["session_id"]
            self.sessions[sid] = {"created_at": datetime.utcnow(), "archived_at": None}
            return MockResult([])

        if "select archived_at from chat_sessions" in stmt_str:
            sid = params["session_id"]
            if sid in self.sessions:
                return MockResult([(self.sessions[sid]["archived_at"],)])
            return MockResult([])

        if "select 1 from chat_sessions" in stmt_str:
            sid = params["session_id"]
            if sid in self.sessions:
                return MockResult([(1,)])
            return MockResult([])

        if "insert into chat_messages" in stmt_str:
            role = "user" if "'user'" in stmt_str else "assistant" if "'assistant'" in stmt_str else params.get("role")
            self.messages.append({
                "message_id": params.get("message_id"),
                "session_id": params.get("session_id"),
                "role": role,
                "content": params.get("content"),
                "timestamp": params.get("timestamp") or datetime.utcnow(),
                "query_text": params.get("query_text"),
                "retrieved_chunk_ids": params.get("retrieved_chunk_ids"),
                "reranking_scores": params.get("reranking_scores"),
                "reranking_provider": params.get("reranking_provider"),
                "reranking_duration_ms": params.get("reranking_duration_ms"),
            })
            return MockResult([])

        if "select message_id" in stmt_str:
            sid = params["session_id"]
            matched = [
                (
                    m["message_id"], m["session_id"], m["role"], m["content"], m["timestamp"],
                    m["query_text"], m["retrieved_chunk_ids"], m["reranking_scores"],
                    m["reranking_provider"], m["reranking_duration_ms"]
                )
                for m in self.messages if m["session_id"] == sid
            ]
            # Match messages sorted by timestamp asc
            matched.sort(key=lambda x: x[4])
            return MockResult(matched)

        if "update chat_sessions" in stmt_str:
            secs = params["seconds"]
            now = datetime.utcnow()
            for sid, sinfo in self.sessions.items():
                if sinfo["archived_at"] is None:
                    delta = (now - sinfo["created_at"]).total_seconds()
                    if delta > secs:
                        sinfo["archived_at"] = now
            return MockResult([])

        return MockResult([])

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unit_embedding_failure_propagation() -> None:
    """Verify that embedding failure propagates as api_unavailable error (Requirement 3.4)."""
    db_session = InMemDbSession()
    session_id = uuid.uuid4()
    db_session.sessions[session_id] = {"created_at": datetime.utcnow(), "archived_at": None}

    # Mock configuration
    mock_config = MagicMock()

    # Mock embedding generator to raise EmbeddingFailureError
    embedding_generator = AsyncMock()
    embedding_generator.generate_embedding.side_effect = EmbeddingFailureError("OpenRouter service down")

    orchestration_engine = AsyncMock()
    llm_service = AsyncMock()

    chat_service = ChatService(
        config_manager=mock_config,
        db_session=db_session,
        embedding_generator=embedding_generator,
        orchestration_engine=orchestration_engine,
        llm_service=llm_service,
    )

    # Verify query raises ChatServiceError with "api_unavailable" code
    with pytest.raises(ChatServiceError) as exc_info:
        await chat_service.query(session_id, "Sample user query")

    assert exc_info.value.error_code == "api_unavailable"
    assert exc_info.value.detail == "Embedding service unavailable."

    # Verify database was NOT committed
    assert not db_session.committed
    assert len(db_session.messages) == 0


@pytest.mark.asyncio
async def test_unit_session_history_context_maintenance() -> None:
    """Verify context and history maintenance across multiple queries within a session (Requirement 11.4)."""
    db_session = InMemDbSession()
    
    # 1. Initialize services
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key: {
        "reranker.reranker_provider": "cohere"
    }[key]

    embedding_generator = AsyncMock()
    embedding_generator.generate_embedding.return_value = [0.1, 0.2]

    # Setup orchestrator to return a valid context chunk
    c = Chunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_text="context chunk text",
        position_in_document=0,
    )
    orchestration_engine = AsyncMock()
    async def mock_orchestrate(query_vector, query_text):
        return ([RankedChunk(chunk=c, score=0.85)], f"prompt with {query_text}")
    orchestration_engine.orchestrate.side_effect = mock_orchestrate

    # Mock responses for different queries
    llm_service = AsyncMock()
    llm_responses = {
        "What is task A?": "Task A is about scheduling.",
        "What is task B?": "Task B is about testing."
    }
    llm_service.generate_response.side_effect = lambda prompt: next(
        (resp for q, resp in llm_responses.items() if q in prompt),
        "Default LLM answer"
    )

    chat_service = ChatService(
        config_manager=mock_config,
        db_session=db_session,
        embedding_generator=embedding_generator,
        orchestration_engine=orchestration_engine,
        llm_service=llm_service,
    )

    # 2. Create session (Requirement 11.1)
    session_id = await chat_service.create_session()
    assert session_id in db_session.sessions

    # 3. Submit Query 1
    query_1 = "What is task A?"
    resp_1 = await chat_service.query(session_id, query_1)
    assert resp_1.answer == "Task A is about scheduling."

    # 4. Submit Query 2
    query_2 = "What is task B?"
    resp_2 = await chat_service.query(session_id, query_2)
    assert resp_2.answer == "Task B is about testing."

    # 5. Fetch history (Requirement 11.3)
    history = await chat_service.get_history(session_id)
    
    # Ensure context is maintained: history has 4 messages in chronological order:
    # 1. user: What is task A?
    # 2. assistant: Task A is about scheduling.
    # 3. user: What is task B?
    # 4. assistant: Task B is about testing.
    assert len(history) == 4

    assert history[0].role == "user"
    assert history[0].content == query_1

    assert history[1].role == "assistant"
    assert history[1].content == "Task A is about scheduling."
    assert history[1].query_text == query_1

    assert history[2].role == "user"
    assert history[2].content == query_2

    assert history[3].role == "assistant"
    assert history[3].content == "Task B is about testing."
    assert history[3].query_text == query_2


@pytest.mark.asyncio
async def test_unit_session_archiving() -> None:
    """Verify that sessions expire and are archived (Requirement 11.5)."""
    db_session = InMemDbSession()
    chat_service = ChatService(db_session=db_session)

    # Create session
    session_id = await chat_service.create_session()
    
    # Manually back-date the session created_at to make it expired (e.g. 25 hours ago)
    db_session.sessions[session_id]["created_at"] = datetime.utcnow() - timedelta(hours=25)

    # Retrieving history should trigger archiving of this session
    # Since it is expired, get_history will archive it first, and check_session in query will raise ValueError
    # Let's test that get_history successfully archives it (archived_at is set)
    history = await chat_service.get_history(session_id)
    assert history == []
    assert db_session.sessions[session_id]["archived_at"] is not None

    # Querying a new query on this session should now reject it since it is archived
    with pytest.raises(ValueError) as exc_info:
        await chat_service.query(session_id, "Hello?")
    assert f"Session '{session_id}' is archived." in str(exc_info.value)
