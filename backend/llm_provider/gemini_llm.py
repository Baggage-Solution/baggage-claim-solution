from __future__ import annotations

import logging
from typing import List, Optional

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from backend.core.exceptions import AppError
from backend.llm_provider.base import LLMProvider

logger = logging.getLogger(__name__)


class GeminiLLMProvider(LLMProvider):
    """
    Gemini Flash LLM implementation for passenger conversation (POC).

    Uses Gemini 2.5 Flash free tier: 1M tokens/day, 1500 req/day.
    Ref: https://ai.google.dev/pricing

    Future swap: set LLM_PROVIDER=claude → implement claude_llm.py
    or LLM_PROVIDER=ollama → implement ollama_llm.py.
    Zero agent code changes needed — only dependencies.py and new provider file.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.2,
    ) -> None:
        """
        Initialise the Gemini LLM provider.

        Args:
            api_key: Gemini API key from GEMINI_API_KEY env var.
            model: Gemini model name. Defaults to gemini-2.5-flash.
            temperature: Sampling temperature. Low = consistent, high = creative.
                         0.2 is appropriate for customer service responses.
        """
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._model_name = model
        self._default_temperature = temperature

    def _build_gemini_contents(self, messages: List[dict]) -> list:
        """
        Convert OpenAI-style message list to Gemini contents format.

        OpenAI format:  [{"role": "user", "content": "hi"},
                          {"role": "assistant", "content": "hello"}]

        Gemini format:  [{"role": "user", "parts": ["hi"]},
                          {"role": "model", "parts": ["hello"]}]

        Note: Gemini uses "model" instead of "assistant" for the AI role.
        System messages are prepended to the first user message content.

        Args:
            messages: List of {role, content} dicts in OpenAI format.

        Returns:
            List of {role, parts} dicts in Gemini format.
        """
        gemini_contents = []
        system_text = ""

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # Gemini doesn't have a system role — prepend to first user turn
                system_text = content
                continue

            if role == "assistant":
                role = "model"

            # Prepend system prompt to the very first user message
            if role == "user" and system_text and not gemini_contents:
                content = f"{system_text}\n\n{content}"
                system_text = ""

            gemini_contents.append({"role": role, "parts": [content]})

        return gemini_contents

    async def chat(
        self,
        messages: List[dict],
        temperature: Optional[float] = None,
    ) -> str:
        """
        Send a list of {role, content} messages and return the assistant reply.

        Converts OpenAI-style messages to Gemini format, calls the API,
        and handles Gemini safety blocks gracefully.

        Args:
            messages: List of {role, content} dicts.
                      Roles: "system", "user", "assistant"
            temperature: Override default temperature for this call.
                         None uses the provider default (0.2).

        Returns:
            Assistant reply as a string.

        Raises:
            AppError: If Gemini blocks the content for safety reasons
                      or returns an empty response.
        """
        temp = temperature if temperature is not None else self._default_temperature

        logger.info(
            "gemini_llm_chat_started",
            extra={
                "model": self._model_name,
                "message_count": len(messages),
                "temperature": temp,
            },
        )

        contents = self._build_gemini_contents(messages)

        generation_config = GenerationConfig(
            temperature=temp,
            max_output_tokens=1024,
        )

        response = self._model.generate_content(
            contents,
            generation_config=generation_config,
        )

        # Handle Gemini safety blocks
        if not response.candidates:
            logger.warning(
                "gemini_llm_no_candidates",
                extra={
                    "prompt_feedback": str(getattr(response, "prompt_feedback", ""))
                },
            )
            raise AppError(
                message="Gemini returned no response — content may have been blocked",
                code="LLM_BLOCKED",
            )

        candidate = response.candidates[0]

        # Check finish reason for safety blocks
        finish_reason = str(getattr(candidate, "finish_reason", "")).upper()
        if "SAFETY" in finish_reason or "BLOCK" in finish_reason:
            logger.warning(
                "gemini_llm_safety_block",
                extra={"finish_reason": finish_reason},
            )
            raise AppError(
                message="Response blocked by Gemini safety filters",
                code="LLM_SAFETY_BLOCK",
            )

        reply = response.text.strip()

        logger.info(
            "gemini_llm_chat_completed",
            extra={
                "model": self._model_name,
                "reply_length": len(reply),
            },
        )

        return reply
