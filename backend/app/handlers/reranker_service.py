"""
RerankerService — reranks retrieved chunks for improved relevance.

Supports Cohere Rerank v3 and Jina Reranker v2.
Implements Requirements: 13.1–13.6, 13.8–13.10.
"""

import logging
import os
import time
from typing import List, Optional

import cohere
import httpx

from app.config.configuration_manager import ConfigurationManager
from app.models.models import Chunk, RankedChunk

logger = logging.getLogger(__name__)


class RerankerError(Exception):
    """Raised when the reranking operation fails or times out."""
    pass


class RerankerService:
    """Reranks document chunks using Jina or Cohere Reranker APIs."""

    def __init__(
        self,
        config_manager: Optional[ConfigurationManager] = None,
        cohere_client: Optional[cohere.Client] = None,
        httpx_client: Optional[httpx.Client] = None,
    ) -> None:
        self.config_manager = config_manager
        self.cohere_api_key = os.getenv("COHERE_API_KEY", "")
        self.jina_api_key = os.getenv("JINA_API_KEY", "")
        
        self._cohere_client = cohere_client
        self._httpx_client = httpx_client

    @property
    def cohere_client(self) -> cohere.Client:
        """Lazy-loaded Cohere client."""
        if self._cohere_client is None:
            self._cohere_client = cohere.Client(
                api_key=self.cohere_api_key,
                timeout=10.0,  # Allow reasonable network latency. Warning is logged if duration > 50ms (Req 13.4).
            )
        return self._cohere_client

    @property
    def httpx_client(self) -> httpx.Client:
        """Lazy-loaded HTTPX client."""
        if self._httpx_client is None:
            # Allow reasonable network latency. Warning is logged if duration > 50ms (Req 13.4).
            self._httpx_client = httpx.Client(timeout=10.0)
        return self._httpx_client

    def rerank(self, query: str, chunks: List[Chunk]) -> List[RankedChunk]:
        """Rerank a list of chunks based on a query.

        Parameters
        ----------
        query : str
            The user query string.
        chunks : List[Chunk]
            The list of retrieved document chunks.

        Returns
        -------
        List[RankedChunk]
            The sorted, ranked chunks (top_k results).
        """
        if not chunks:
            return []

        # Retrieve settings from ConfigurationManager (Requirement 13.6)
        provider = "cohere"
        model_name = "rerank-english-v3.0"
        top_k = 5

        if self.config_manager:
            try:
                provider = self.config_manager.get("reranker.reranker_provider")
                model_name = self.config_manager.get("reranker.reranker_model_name")
                top_k = self.config_manager.get("reranker.reranker_top_k")
            except Exception as exc:
                logger.warning("Failed to retrieve reranker config: %s", exc)

        start_time = time.perf_counter()

        try:
            if provider == "cohere":
                ranked = self._rerank_cohere(query, chunks, model_name, top_k)
            elif provider == "jina":
                ranked = self._rerank_jina(query, chunks, model_name, top_k)
            else:
                raise RerankerError(f"Unsupported reranker provider: {provider}")
        except Exception as exc:
            logger.error("Reranking failed: %s", exc)
            if isinstance(exc, RerankerError):
                raise
            raise RerankerError(f"Reranking service error: {exc}") from exc

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Log performance warning if it exceeds 50 ms (Requirement 13.4, 3.14)
        if elapsed_ms > 50.0:
            logger.warning(
                "Reranker performance warning: reranking took %.2f ms (limit: 50 ms)",
                elapsed_ms,
            )

        return ranked

    def _rerank_cohere(
        self, query: str, chunks: List[Chunk], model_name: str, top_k: int
    ) -> List[RankedChunk]:
        """Rerank using Cohere Rerank API."""
        try:
            response = self.cohere_client.rerank(
                model=model_name,
                query=query,
                documents=[c.chunk_text for c in chunks],
                top_n=top_k,
            )
            
            ranked_chunks = []
            for result in response.results:
                idx = result.index
                score = result.relevance_score
                # Bounded score between 0.0 and 1.0 (Requirement 13.8)
                bounded_score = max(0.0, min(1.0, float(score)))
                ranked_chunks.append(RankedChunk(chunk=chunks[idx], score=bounded_score))
                
            # Ensure they are sorted by descending score (Requirement 13.5)
            ranked_chunks.sort(key=lambda x: x.score, reverse=True)
            return ranked_chunks
        except Exception as exc:
            raise RerankerError(f"Cohere API failure: {exc}") from exc

    def _rerank_jina(
        self, query: str, chunks: List[Chunk], model_name: str, top_k: int
    ) -> List[RankedChunk]:
        """Rerank using Jina Reranker API."""
        try:
            response = self.httpx_client.post(
                "https://api.jina.ai/v1/rerank",
                headers={
                    "Authorization": f"Bearer {self.jina_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "query": query,
                    "documents": [c.chunk_text for c in chunks],
                    "top_n": top_k,
                },
            )
            response.raise_for_status()
            
            data = response.json()
            ranked_chunks = []
            for result in data.get("results", []):
                idx = result["index"]
                score = result["relevance_score"]
                # Bounded score between 0.0 and 1.0 (Requirement 13.8)
                bounded_score = max(0.0, min(1.0, float(score)))
                ranked_chunks.append(RankedChunk(chunk=chunks[idx], score=bounded_score))
                
            # Ensure they are sorted by descending score (Requirement 13.5)
            ranked_chunks.sort(key=lambda x: x.score, reverse=True)
            return ranked_chunks
        except Exception as exc:
            raise RerankerError(f"Jina API failure: {exc}") from exc
