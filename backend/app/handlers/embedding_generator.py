"""
EmbeddingGenerator — wraps OpenRouter embedding API calls with retry logic and timeouts.

Implements Requirements: 2.5, 2.6, 3.3, 3.4.
"""

import asyncio
import logging
import os
import httpx
from typing import List, Optional
from openai import AsyncOpenAI, APITimeoutError, APIConnectionError, APIStatusError

from app.config.configuration_manager import ConfigurationManager

logger = logging.getLogger(__name__)


class EmbeddingFailureError(Exception):
    """Raised when embedding generation fails after all retry attempts."""
    pass


class EmbeddingGenerator:
    """Generates text embeddings using OpenRouter's embedding API.

    Parameters
    ----------
    config_manager : ConfigurationManager, optional
        Configuration manager to retrieve active model settings.
    """

    def __init__(self, config_manager: Optional[ConfigurationManager] = None) -> None:
        self.config_manager = config_manager
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.base_url = "https://openrouter.ai/api/v1"
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> AsyncOpenAI:
        """Lazy-loaded AsyncOpenAI client configured for OpenRouter."""
        if self._client is None:
            # Enforce 30s timeout per attempt (Requirement 2.5)
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._client

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate a vector embedding for a single text chunk."""
        embeddings = await self.generate_embeddings([text])
        return embeddings[0]

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate vector embeddings for a list of text chunks in batches."""
        model_name = "openai/text-embedding-3-small"
        if self.config_manager:
            try:
                model_name = self.config_manager.get("models.embedding_model_name")
            except Exception as exc:
                logger.warning("Failed to retrieve embedding model from config: %s", exc)

        retries = 3
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        all_embeddings = []
        batch_size = 20
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                backoff = 1.0
                batch_success = False
                
                for attempt in range(1, retries + 1):
                    try:
                        logger.debug(
                            "Attempting embedding generation (attempt %d/%d) using model %s via direct HTTP",
                            attempt, retries, model_name
                        )
                        res = await client.post(
                            f"{self.base_url}/embeddings",
                            headers=headers,
                            json={
                                "input": batch_texts,
                                "model": model_name,
                            },
                        )
                        if res.status_code != 200:
                            raise RuntimeError(f"HTTP status code {res.status_code}: {res.text}")
                        
                        res_json = res.json()
                        if "error" in res_json:
                            err_msg = res_json["error"].get("message", str(res_json["error"]))
                            raise RuntimeError(f"API Error: {err_msg}")
                        
                        if "data" not in res_json or not res_json["data"]:
                            raise RuntimeError(f"Invalid response payload: {res_json}")
                        
                        # Sort data by index to ensure original order
                        data_sorted = sorted(res_json["data"], key=lambda x: x.get("index", 0))
                        batch_embeddings = [item["embedding"] for item in data_sorted]
                        all_embeddings.extend(batch_embeddings)
                        batch_success = True
                        break
                    except Exception as exc:
                        logger.warning(
                            "Embedding generation attempt %d failed with error: %s. Retrying in %.1f s...",
                            attempt, exc, backoff
                        )
                        if attempt == retries:
                            raise EmbeddingFailureError(
                                f"Embedding generation failed after {retries} attempts. Last error: {exc}"
                            ) from exc
                        await asyncio.sleep(backoff)
                        backoff *= 2.0
                        
                if not batch_success:
                    raise EmbeddingFailureError("Embedding generation failed after maximum retries.")
                    
        return all_embeddings

