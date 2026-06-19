"""
OrchestrationEngine — coordinates vector retrieval, reranking, and prompt construction.

Implements Requirements: 3.5, 3.6, 3.7, 3.8, 10.1–10.11, 13.7.
"""

import asyncio
import logging
import os
import time
from typing import List, Optional, Tuple
import uuid

from qdrant_client import QdrantClient

from app.config.configuration_manager import ConfigurationManager
from app.handlers.reranker_service import RerankerService
from app.models.models import Chunk, RankedChunk

logger = logging.getLogger(__name__)


class OrchestrationError(Exception):
    """Raised when the orchestration engine encounters an error or timeout."""
    pass


class OrchestrationEngine:
    """Coordinates retrieval, reranking, and prompt construction for the RAG chatbot."""

    QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
    QDRANT_COLLECTION = "document_chunks"

    DEFAULT_PROMPT_TEMPLATE = (
        "{system_instructions}\n\n"
        "Context:\n"
        "{context_chunks}\n\n"
        "Query: {user_query}"
    )

    def __init__(
        self,
        config_manager: Optional[ConfigurationManager] = None,
        qdrant_client: Optional[QdrantClient] = None,
        reranker_service: Optional[RerankerService] = None,
    ) -> None:
        self.config_manager = config_manager
        self._qdrant_client = qdrant_client
        self._reranker_service = reranker_service

    @property
    def qdrant_client(self) -> QdrantClient:
        """Lazy-loaded Qdrant client. Supports self-hosted and Qdrant Cloud."""
        if self._qdrant_client is None:
            use_local = os.getenv("USE_LOCAL_MODE", "false").lower() == "true"
            if use_local:
                self._qdrant_client = QdrantClient(path="./data/qdrant")
            else:
                qdrant_url = os.getenv("QDRANT_URL")
                qdrant_api_key = os.getenv("QDRANT_API_KEY")
                if qdrant_url:
                    self._qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
                else:
                    self._qdrant_client = QdrantClient(
                        host=self.QDRANT_HOST,
                        port=self.QDRANT_PORT,
                    )
        return self._qdrant_client

    @property
    def reranker_service(self) -> RerankerService:
        """Lazy-loaded RerankerService."""
        if self._reranker_service is None:
            self._reranker_service = RerankerService(self.config_manager)
        return self._reranker_service

    async def orchestrate(
        self, 
        query_vector: List[float], 
        query_text: str, 
        document_ids: Optional[List[uuid.UUID]] = None
    ) -> Tuple[List[RankedChunk], str]:
        """Coordinate retrieval, reranking, and prompt construction.

        Parameters
        ----------
        query_vector : List[float]
            The embedding vector for the user query.
        query_text : str
            The raw text of the user query.

        Returns
        -------
        Tuple[List[RankedChunk], str]
            A tuple of (selected ranked chunks, formatted prompt).
        """
        # 1. Retrieve config options
        retrieval_top_k = 20
        max_chunks_evaluated = 100
        similarity_threshold = 0.7
        reranker_top_k = 5
        prompt_max_chars = 8000
        system_instructions = (
            "You are a helpful assistant that answers questions based on the provided document context."
        )
        prompt_template = self.DEFAULT_PROMPT_TEMPLATE

        if self.config_manager:
            try:
                retrieval_top_k = self.config_manager.get("retrieval.top_k")
                max_chunks_evaluated = self.config_manager.get("retrieval.max_chunks_evaluated")
                similarity_threshold = self.config_manager.get("retrieval.similarity_threshold")
                reranker_top_k = self.config_manager.get("reranker.reranker_top_k")
                prompt_max_chars = self.config_manager.get("retrieval.prompt_max_chars")
                system_instructions = self.config_manager.get("prompt_templates.system_instructions")
            except Exception as exc:
                logger.warning("Failed to retrieve config parameters; using defaults. Error: %s", exc)

        # Enforce maximum chunk evaluation bounded at 100 (Requirement 10.11 / Property 23)
        retrieval_limit = min(retrieval_top_k, max_chunks_evaluated, 100)

        # 2. Retrieve chunks from Vector Store
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            qdrant_filter = None
            if document_ids is not None:
                if len(document_ids) == 0:
                    logger.info("No documents selected (General Chat Mode). Skipping retrieval.")
                    return [], ""

                qdrant_filter = Filter(
                    should=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=str(doc_id))
                        ) for doc_id in document_ids
                    ]
                )

            # Enforce 30-second timeout on retrieval (Requirement 10.8)
            results = await asyncio.wait_for(
                asyncio.to_thread(
                    self.qdrant_client.search,
                    collection_name=self.QDRANT_COLLECTION,
                    query_vector=query_vector,
                    limit=retrieval_limit,
                    query_filter=qdrant_filter,
                ),
                timeout=30.0
            )
        except asyncio.TimeoutError as exc:
            logger.error("Retrieval timed out after 30 seconds.")
            raise OrchestrationError("Retrieval timeout") from exc
        except Exception as exc:
            logger.error("Failed to query Qdrant: %s", exc)
            raise OrchestrationError(f"Vector store search failed: {exc}") from exc

        # 3. Process retrieved results, clamp similarity scores to [0.0, 1.0] (Requirement 10.1 / Property 21)
        scored_chunks = []
        for point in results:
            payload = point.payload or {}
            
            # Reconstruct Chunk model
            try:
                chunk = Chunk(
                    chunk_id=uuid.UUID(payload.get("chunk_id", str(uuid.uuid4()))),
                    document_id=uuid.UUID(payload.get("document_id", str(uuid.uuid4()))),
                    chunk_text=payload.get("chunk_text", ""),
                    position_in_document=int(payload.get("position_in_document", 0)),
                    contextual_summary=payload.get("contextual_summary"),
                    token_count=payload.get("token_count"),
                )
            except Exception as exc:
                logger.warning("Failed to parse chunk payload for point %s: %s", point.id, exc)
                continue

            clamped_score = max(0.0, min(1.0, float(point.score)))
            scored_chunks.append((chunk, clamped_score))

        # 4. Sort by descending similarity score (Requirement 10.2 / Property 22)
        scored_chunks.sort(key=lambda x: x[1], reverse=True)

        # 5. Check similarity threshold (Requirement 10.10 / Property 16)
        # If all similarity scores are strictly below similarity_threshold, return no-results response
        if not scored_chunks or all(score < similarity_threshold for _, score in scored_chunks):
            logger.info("No relevant chunks found above similarity threshold %s.", similarity_threshold)
            return [], ""

        # Prepare Chunk list for reranking
        retrieved_chunks = [item[0] for item in scored_chunks]

        # 6. Rerank retrieved chunks
        try:
            top_k_ranked = self.reranker_service.rerank(query_text, retrieved_chunks)
        except Exception as exc:
            # Fall back to original similarity ordering on reranker failure (Requirement 13.7 / Property 27)
            logger.warning("Reranking failed. Falling back to vector similarity scores. Error: %s", exc)
            top_k_ranked = [
                RankedChunk(chunk=chunk, score=score)
                for chunk, score in scored_chunks
            ]

        # Ensure we sort the ranked chunks in descending order of score (Requirement 13.5 / Property 26)
        # And select the top top_k chunks (Requirement 3.7, 10.3 / Property 13)
        top_k_ranked = sorted(top_k_ranked, key=lambda x: x.score, reverse=True)
        selected_ranked = top_k_ranked[:reranker_top_k]

        # 7. Construct prompt with context truncation (Requirement 3.8, 10.5, 10.6, 10.7 / Property 14, 15)
        context_chunks_str = "\n".join([rc.chunk.chunk_text for rc in selected_ranked])

        empty_context_prompt = prompt_template.format(
            system_instructions=system_instructions,
            context_chunks="",
            user_query=query_text
        )

        max_context_chars = prompt_max_chars - len(empty_context_prompt)

        if max_context_chars < 0:
            context_chunks_str = ""
        elif len(context_chunks_str) > max_context_chars:
            context_chunks_str = context_chunks_str[:max_context_chars]

        final_prompt = prompt_template.format(
            system_instructions=system_instructions,
            context_chunks=context_chunks_str,
            user_query=query_text
        )

        return selected_ranked, final_prompt
