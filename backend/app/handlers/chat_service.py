"""
ChatService — orchestrates the RAG query lifecycle, session management, and history.

Implements Requirements: 3.4, 3.10–3.13, 11.1–11.6, 13.10.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import text

from app.config.configuration_manager import ConfigurationManager
from app.db.connection import get_db
from app.handlers.embedding_generator import EmbeddingGenerator, EmbeddingFailureError
from app.handlers.guardrail_system import GuardrailSystem, GuardrailViolationError
from app.handlers.input_validator import InputValidator, InputValidationError
from app.handlers.llm_service import LLMService, LLMResponseError
from app.handlers.orchestration_engine import OrchestrationEngine
from app.models.models import ChatMessage, ChatResponse, RankedChunk

logger = logging.getLogger(__name__)


class ChatServiceError(Exception):
    """Exception raised when the chat service encounters an error."""

    def __init__(self, error_code: str, detail: str) -> None:
        self.error_code = error_code
        self.detail = detail
        super().__init__(detail)


class ChatService:
    """Manages chat sessions and coordinates RAG query pipeline execution.

    Parameters
    ----------
    config_manager : ConfigurationManager, optional
        Configuration manager instance.
    db_session : AsyncSession, optional
        Database session for executing queries.
    input_validator : InputValidator, optional
        Helper for validating and sanitizing queries.
    guardrail_system : GuardrailSystem, optional
        Helper for detecting prompt injections and scope.
    embedding_generator : EmbeddingGenerator, optional
        Helper for generating embeddings.
    orchestration_engine : OrchestrationEngine, optional
        Helper for RAG pipelines.
    llm_service : LLMService, optional
        Helper for generating LLM text responses.
    """

    def __init__(
        self,
        config_manager: Optional[ConfigurationManager] = None,
        db_session=None,
        input_validator: Optional[InputValidator] = None,
        guardrail_system: Optional[GuardrailSystem] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        orchestration_engine: Optional[OrchestrationEngine] = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        self.config_manager = config_manager
        self._db_session = db_session
        self._input_validator = input_validator
        self._guardrail_system = guardrail_system
        self._embedding_generator = embedding_generator
        self._orchestration_engine = orchestration_engine
        self._llm_service = llm_service

    @property
    def input_validator(self) -> InputValidator:
        """Lazy-loaded InputValidator."""
        if self._input_validator is None:
            self._input_validator = InputValidator()
        return self._input_validator

    @property
    def guardrail_system(self) -> GuardrailSystem:
        """Lazy-loaded GuardrailSystem."""
        if self._guardrail_system is None:
            self._guardrail_system = GuardrailSystem()
        return self._guardrail_system

    @property
    def embedding_generator(self) -> EmbeddingGenerator:
        """Lazy-loaded EmbeddingGenerator."""
        if self._embedding_generator is None:
            self._embedding_generator = EmbeddingGenerator(self.config_manager)
        return self._embedding_generator

    @property
    def orchestration_engine(self) -> OrchestrationEngine:
        """Lazy-loaded OrchestrationEngine."""
        if self._orchestration_engine is None:
            self._orchestration_engine = OrchestrationEngine(self.config_manager)
        return self._orchestration_engine

    @property
    def llm_service(self) -> LLMService:
        """Lazy-loaded LLMService."""
        if self._llm_service is None:
            self._llm_service = LLMService(self.config_manager)
        return self._llm_service

    async def _execute_db(self, func):
        """Helper to run database operations on injected or direct sessions."""
        if self._db_session is not None:
            return await func(self._db_session)
        else:
            async for session in get_db():
                return await func(session)

    async def create_session(self) -> uuid.UUID:
        """Create a new chat session with a unique UUID.

        Returns
        -------
        uuid.UUID
            The created session ID.
        """
        async def _create(session):
            session_id = uuid.uuid4()
            use_local = os.getenv("USE_LOCAL_MODE", "false").lower() == "true"
            stmt = text(
                """
                INSERT INTO chat_sessions (session_id, created_at)
                VALUES (:session_id, CURRENT_TIMESTAMP)
                """ if use_local else """
                INSERT INTO chat_sessions (session_id, created_at)
                VALUES (:session_id, NOW())
                """
            )
            await session.execute(stmt, {"session_id": str(session_id) if use_local else session_id})
            await session.commit()
            return session_id

        return await self._execute_db(_create)

    async def archive_expired_sessions(self, expiration_seconds: float = 86400.0) -> None:
        """Archive sessions that have expired (created_at older than expiration_seconds).

        Parameters
        ----------
        expiration_seconds : float, optional
            Number of seconds after creation a session expires. Default is 24 hours.
        """
        async def _archive(session):
            use_local = os.getenv("USE_LOCAL_MODE", "false").lower() == "true"
            stmt = text(
                """
                UPDATE chat_sessions
                SET archived_at = CURRENT_TIMESTAMP
                WHERE archived_at IS NULL 
                  AND created_at < datetime('now', '-' || :seconds || ' seconds')
                """ if use_local else """
                UPDATE chat_sessions
                SET archived_at = NOW()
                WHERE archived_at IS NULL 
                  AND created_at < NOW() - (:seconds * INTERVAL '1 second')
                """
            )
            await session.execute(stmt, {"seconds": expiration_seconds})
            await session.commit()

        await self._execute_db(_archive)

    async def get_history(self, session_id: uuid.UUID) -> List[ChatMessage]:
        """Returns stored messages for the session after archiving expired sessions.

        Parameters
        ----------
        session_id : UUID
            The chat session ID.

        Returns
        -------
        List[ChatMessage]
            Stored messages sorted ascending by timestamp.
        """
        # Archive expired sessions first (Requirement 11.5)
        await self.archive_expired_sessions()

        async def _check_exists(session):
            use_local = os.getenv("USE_LOCAL_MODE", "false").lower() == "true"
            stmt = text("SELECT 1 FROM chat_sessions WHERE session_id = :session_id")
            res = await session.execute(stmt, {"session_id": str(session_id) if use_local else session_id})
            return res.fetchone() is not None

        if not await self._execute_db(_check_exists):
            raise ValueError(f"Session '{session_id}' not found.")

        async def _get(session):
            stmt = text(
                """
                SELECT message_id, session_id, role, content, timestamp, 
                       query_text, retrieved_chunk_ids, reranking_scores, 
                       reranking_provider, reranking_duration_ms
                FROM chat_messages
                WHERE session_id = :session_id
                ORDER BY timestamp ASC
                """
            )
            res = await session.execute(stmt, {"session_id": session_id})
            rows = res.fetchall()
            
            messages = []
            use_local = os.getenv("USE_LOCAL_MODE", "false").lower() == "true"
            for row in rows:
                c_ids = row[6]
                s_scores = row[7]
                if use_local:
                    c_ids = json.loads(c_ids) if c_ids else []
                    s_scores = json.loads(s_scores) if s_scores else []
                
                messages.append(
                    ChatMessage(
                        message_id=row[0],
                        session_id=row[1],
                        role=row[2],
                        content=row[3],
                        timestamp=row[4],
                        query_text=row[5],
                        retrieved_chunk_ids=c_ids,
                        reranking_scores=s_scores,
                        reranking_provider=row[8],
                        reranking_duration_ms=row[9],
                    )
                )
            return messages

        return await self._execute_db(_get)

    async def query(
        self, 
        session_id: uuid.UUID, 
        user_query: str, 
        document_ids: Optional[List[uuid.UUID]] = None
    ) -> ChatResponse:
        """End-to-end query handling for RAG Chat.

        Parameters
        ----------
        session_id : UUID
            The current active session ID.
        user_query : str
            The raw query submitted by the user.

        Returns
        -------
        ChatResponse
            The structured chat response containing the answer and context metadata.

        Raises
        ------
        ChatServiceError
            On embedding failures, LLM timeouts, and validation/guardrail rejections.
        """
        # Check session status
        async def _check_session(session):
            stmt = text(
                """
                SELECT archived_at FROM chat_sessions
                WHERE session_id = :session_id
                """
            )
            use_local = os.getenv("USE_LOCAL_MODE", "false").lower() == "true"
            res = await session.execute(stmt, {"session_id": str(session_id) if use_local else session_id})
            row = res.fetchone()
            if not row:
                raise ValueError(f"Session '{session_id}' not found.")
            if row[0] is not None:
                raise ValueError(f"Session '{session_id}' is archived.")

        await self._execute_db(_check_session)

        # 1. Validate query (Requirement 3.1)
        try:
            self.input_validator.validate_query(user_query)
        except InputValidationError as exc:
            raise ChatServiceError(exc.error_code, exc.detail) from exc

        # 2. Sanitize query (Requirement 3.2, 4.7)
        sanitized_query = self.input_validator.sanitize_query(user_query)

        # 3. Guardrail check (Requirement 4.1, 4.2, 4.3, 4.8, 4.9)
        try:
            self.guardrail_system.validate_query(sanitized_query)
        except GuardrailViolationError as exc:
            raise ChatServiceError(exc.error_code, exc.detail) from exc

        # 4. Generate Query Embedding (Requirement 3.3, 3.4)
        try:
            query_vector = await self.embedding_generator.generate_embedding(sanitized_query)
        except EmbeddingFailureError as exc:
            logger.error("Embedding generation failed in chat service query: %s", exc)
            raise ChatServiceError("api_unavailable", "Embedding service unavailable.") from exc

        # 5. Run query through Orchestration Engine and capture reranking duration
        reranker = self.orchestration_engine.reranker_service
        original_rerank = reranker.rerank
        reranking_duration_ms = None

        def wrapped_rerank(*args, **kwargs):
            nonlocal reranking_duration_ms
            t0 = time.perf_counter()
            try:
                return original_rerank(*args, **kwargs)
            finally:
                reranking_duration_ms = (time.perf_counter() - t0) * 1000

        reranker.rerank = wrapped_rerank
        try:
            selected_ranked, formatted_prompt = await self.orchestration_engine.orchestrate(
                query_vector, sanitized_query, document_ids
            )
        finally:
            reranker.rerank = original_rerank

        # Determine Reranking Provider
        reranking_provider = None
        if self.config_manager:
            try:
                reranking_provider = self.config_manager.get("reranker.reranker_provider")
            except Exception:
                pass
        if reranking_provider is None:
            reranking_provider = "cohere"

        # 6. Check for no relevant context threshold (Requirement 3.13)
        if not formatted_prompt:
            formatted_prompt = (
                f"System: You are a helpful AI assistant. You could not find relevant context "
                f"in the uploaded documents for this question. Inform the user of this politely, "
                f"and optionally provide a general helpful answer.\n\nUser: {user_query}"
            )

        # Load conversation history for context (Requirement 11.2)
        history_messages = []
        try:
            prev_messages = await self.get_history(session_id)
            for msg in prev_messages:
                history_messages.append({"role": msg.role, "content": msg.content})
        except Exception as exc:
            logger.warning("Failed to load history for LLM context: %s", exc)

        # 7. Generate response using OpenRouter language model (Requirement 3.9, 3.10)
        try:
            answer = await self.llm_service.generate_response(formatted_prompt, history_messages=history_messages)
        except LLMResponseError as exc:
            logger.error("LLM response generation failed in chat service: %s", exc)
            raise ChatServiceError("response_failure", "Response generation failed.") from exc

        # 8. Persist query & response in database metadata store (Requirement 3.12, 11.2, 11.6, 13.10)
        await self._persist_interaction(
            session_id=session_id,
            user_query=user_query,
            answer=answer,
            retrieved_chunks=selected_ranked,
            reranking_provider=reranking_provider,
            reranking_duration_ms=reranking_duration_ms
        )

        return ChatResponse(
            answer=answer,
            session_id=session_id,
            retrieved_chunks=selected_ranked,
            reranking_scores=[rc.score for rc in selected_ranked],
            reranking_provider=reranking_provider,
            reranking_duration_ms=reranking_duration_ms
        )

    async def _persist_interaction(
        self,
        session_id: uuid.UUID,
        user_query: str,
        answer: str,
        retrieved_chunks: List[RankedChunk],
        reranking_provider: str,
        reranking_duration_ms: Optional[float]
    ) -> None:
        """Write user query and assistant response messages to PostgreSQL."""
        async def _persist(session):
            user_msg_id = uuid.uuid4()
            assistant_msg_id = uuid.uuid4()
            now = datetime.utcnow()

            use_local = os.getenv("USE_LOCAL_MODE", "false").lower() == "true"
            # Insert User message
            stmt_user = text(
                """
                INSERT INTO chat_messages (message_id, session_id, role, content, timestamp)
                VALUES (:message_id, :session_id, 'user', :content, :timestamp)
                """
            )
            await session.execute(
                stmt_user,
                {
                    "message_id": str(user_msg_id) if use_local else user_msg_id,
                    "session_id": str(session_id) if use_local else session_id,
                    "content": user_query,
                    "timestamp": now
                }
            )

            # Insert Assistant message
            stmt_assistant = text(
                """
                INSERT INTO chat_messages (
                    message_id, session_id, role, content, timestamp, query_text,
                    retrieved_chunk_ids, reranking_scores, reranking_provider, reranking_duration_ms
                )
                VALUES (
                    :message_id, :session_id, 'assistant', :content, :timestamp, :query_text,
                    :retrieved_chunk_ids, :reranking_scores, :reranking_provider, :reranking_duration_ms
                )
                """
            )
            
            chunk_ids = [str(rc.chunk.chunk_id) for rc in retrieved_chunks]
            scores = [float(rc.score) for rc in retrieved_chunks]

            use_local = os.getenv("USE_LOCAL_MODE", "false").lower() == "true"
            if use_local:
                chunk_ids_val = json.dumps(chunk_ids)
                scores_val = json.dumps(scores)
            else:
                chunk_ids_val = chunk_ids
                scores_val = scores

            await session.execute(
                stmt_assistant,
                {
                    "message_id": str(assistant_msg_id) if use_local else assistant_msg_id,
                    "session_id": str(session_id) if use_local else session_id,
                    "content": answer,
                    "timestamp": now,
                    "query_text": user_query,
                    "retrieved_chunk_ids": chunk_ids_val,
                    "reranking_scores": scores_val,
                    "reranking_provider": reranking_provider,
                    "reranking_duration_ms": reranking_duration_ms
                }
            )
            await session.commit()

        await self._execute_db(_persist)
