from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class LLMProvider(ABC):
    """
    Abstract interface for LLM-based text generation.
    Swap by changing LLM_PROVIDER env var.
    Future: implement ClaudeLLMProvider, OpenAILLMProvider, OllamaLLMProvider.
    """

    @abstractmethod
    async def chat(self, messages: List[dict], temperature: float | None = None) -> str:
        """
        Send a list of {role, content} messages and return the assistant reply.
        messages format: [{"role": "user", "content": "..."}, ...]
        """
        raise NotImplementedError
