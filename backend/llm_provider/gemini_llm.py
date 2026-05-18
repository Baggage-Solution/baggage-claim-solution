from __future__ import annotations

import logging
from typing import List

from backend.llm_provider.base import LLMProvider

logger = logging.getLogger(__name__)


class GeminiLLMProvider(LLMProvider):
    """
    Gemini Flash LLM implementation (POC — 1M tokens/day free).
    Future swap: set LLM_PROVIDER=claude → claude_llm.py, or LLM_PROVIDER=ollama → ollama_llm.py.
    """

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash", temperature: float = 0.2) -> None:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._default_temperature = temperature

    async def chat(self, messages: List[dict], temperature: float | None = None) -> str:
        # TODO (T-008):
        # 1. Convert messages list to Gemini content format
        # 2. Call self._model.generate_content(content, generation_config={temperature: ...})
        # 3. Return response.text
        # 4. Handle safety blocks (Gemini may block certain content) → raise UpstreamServiceError
        logger.info("gemini_llm_chat", extra={"message_count": len(messages)})
        return "[LLM stub] response"
