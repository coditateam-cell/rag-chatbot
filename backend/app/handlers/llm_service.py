"""
LLMService — wraps OpenRouter language model API calls with timeouts.

Implements Requirements: 3.9, 3.10
"""

import logging
import os
from typing import Optional
from openai import AsyncOpenAI, APITimeoutError, APIConnectionError, APIStatusError

from app.config.configuration_manager import ConfigurationManager

logger = logging.getLogger(__name__)


class LLMResponseError(Exception):
    """Raised when LLM response generation fails."""
    pass


class LLMService:
    """Generates text completions using OpenRouter's language models.

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
            # Enforce 90s timeout per attempt (Requirement 3.9)
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=90.0,
            )
        return self._client

    async def generate_response(self, prompt: str, history_messages: Optional[list] = None) -> str:
        """Generate response for the formatted prompt.

        Parameters
        ----------
        prompt : str
            The constructed and formatted prompt string.
        history_messages : Optional[list]
            A list of dictionary objects containing previous role and content messages.

        Returns
        -------
        str
            The response text content from the language model.

        Raises
        ------
        LLMResponseError
            If response generation fails or times out.
        """
        model_name = "openai/gpt-4o"
        fallback_models = []
        if self.config_manager:
            try:
                model_name = self.config_manager.get("models.llm_model_name")
                fallback_models = self.config_manager.get("models.llm_fallback_models")
            except Exception as exc:
                logger.warning("Failed to retrieve LLM model names from config: %s", exc)

        models_to_try = [model_name] + fallback_models
        last_exception = None

        # Build messages payload
        api_messages = []
        if history_messages:
            for msg in history_messages:
                api_messages.append({"role": msg["role"], "content": msg["content"]})
        api_messages.append({"role": "user", "content": prompt})

        for current_model in models_to_try:
            try:
                logger.debug("Generating response using LLM model: %s", current_model)
                response = await self.client.chat.completions.create(
                    model=current_model,
                    messages=api_messages,
                    max_tokens=2000,
                )
                content = response.choices[0].message.content
                if content is None:
                    raise LLMResponseError(f"LLM response returned empty content for model {current_model}.")
                return content
            except (APITimeoutError, APIConnectionError, APIStatusError) as exc:
                logger.warning("LLM response generation failed for %s: %s. Trying next model...", current_model, exc)
                last_exception = exc
                continue
            except Exception as exc:
                logger.warning("Unexpected LLM failure for %s: %s. Trying next model...", current_model, exc)
                last_exception = exc
                continue

        logger.error("All LLM models failed. Last error: %s", last_exception)
        raise LLMResponseError(f"All LLM models failed. Last error: {last_exception}") from last_exception
