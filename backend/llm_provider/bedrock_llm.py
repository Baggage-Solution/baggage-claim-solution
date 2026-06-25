from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

import boto3
from botocore.exceptions import ClientError

from backend.core.exceptions import AppError
from backend.llm_provider.base import LLMProvider

logger = logging.getLogger(__name__)

# Bedrock's Anthropic Messages API version — a protocol version, not a model
# version. Fixed by AWS for all Claude-on-Bedrock InvokeModel calls; this is
# not the model ID and does not change when the model does.
BEDROCK_ANTHROPIC_VERSION = "bedrock-2023-05-31"


class BedrockLLMProvider(LLMProvider):
    """
    AWS Bedrock (Claude) LLM implementation for passenger conversation (Production).

    Wraps boto3's bedrock-runtime InvokeModel API using Anthropic's Messages
    API request shape. Model ID, region, and temperature all come from
    Settings — never hardcoded here — so swapping to a different Claude
    version or a different region is a config change, not a code change.

    Future swap: set LLM_PROVIDER=openai → implement openai_llm.py, or
    LLM_PROVIDER=ollama → implement ollama_llm.py. Zero agent code changes
    needed — only dependencies.py and the new provider file.
    """

    def __init__(
        self,
        model_id: str,
        region: str,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> None:
        """
        Initialise the Bedrock LLM provider.

        Args:
            model_id: Bedrock model ID for Claude (e.g.
                "anthropic.claude-sonnet-4-20250514-v1:0"). Read from
                Settings.bedrock_llm_model — never hardcoded.
            region: AWS region the Bedrock endpoint lives in (e.g. us-east-1).
            temperature: Sampling temperature. Low = consistent, high = creative.
                0.2 is appropriate for customer service responses.
            max_output_tokens: Maximum tokens Claude may generate per reply.
        """
        self._model_id = model_id
        self._default_temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def _build_anthropic_messages(self, messages: List[dict]) -> tuple[list, str]:
        """
        Convert OpenAI-style message list to Anthropic Messages API format.

        OpenAI format:    [{"role": "user", "content": "hi"},
                            {"role": "assistant", "content": "hello"}]

        Anthropic format: messages=[{"role": "user", "content": "hi"},
                                     {"role": "assistant", "content": "hello"}]
                           system="<system prompt as a separate top-level field>"

        Unlike Gemini, Anthropic's "assistant" role name matches OpenAI's, so
        no role renaming is needed — only the system message needs to be
        pulled out into its own field rather than being a message in the list.

        Args:
            messages: List of {role, content} dicts in OpenAI format.

        Returns:
            Tuple of (anthropic_messages, system_prompt). system_prompt is
            an empty string if no system message was present.
        """
        anthropic_messages = []
        system_text = ""

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # Anthropic uses a dedicated top-level `system` field, not a
                # message in the list — concatenate if multiple system
                # messages are passed (unusual, but don't silently drop any).
                system_text = f"{system_text}\n\n{content}".strip()
                continue

            anthropic_messages.append({"role": role, "content": content})

        return anthropic_messages, system_text

    async def _call_with_retry(self, body: dict) -> dict:
        """
        Call Bedrock InvokeModel with exponential backoff on throttling.

        boto3 is synchronous, so the actual network call is offloaded to a
        thread via asyncio.to_thread to avoid blocking the FastAPI event
        loop — the same pattern used by S3StorageProvider (P-004).

        Args:
            body: Fully-formed Anthropic Messages API request body.

        Returns:
            Parsed JSON response body from Bedrock.

        Raises:
            Exception: Re-raises after all retries are exhausted, or
                immediately for non-throttling errors.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    self._client.invoke_model,
                    modelId=self._model_id,
                    body=json.dumps(body),
                )
                return json.loads(response["body"].read())
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "")
                is_throttled = error_code in (
                    "ThrottlingException",
                    "ServiceQuotaExceededException",
                    "TooManyRequestsException",
                )
                if is_throttled and attempt < 2:
                    wait_secs = 30 * (2**attempt)  # 30s → 60s
                    logger.warning(
                        "bedrock_llm_throttled",
                        extra={
                            "model": self._model_id,
                            "attempt": attempt + 1,
                            "wait_secs": wait_secs,
                            "error_code": error_code,
                        },
                    )
                    last_exc = exc
                    await asyncio.sleep(wait_secs)
                else:
                    raise

        raise last_exc

    async def chat(
        self,
        messages: List[dict],
        temperature: Optional[float] = None,
    ) -> str:
        """
        Send a list of {role, content} messages and return the assistant reply.

        Converts OpenAI-style messages to the Anthropic Messages API shape,
        calls Bedrock InvokeModel, and handles content-filter stops the same
        way GeminiLLMProvider handles safety blocks — by raising AppError
        rather than returning a confusing empty string.

        Args:
            messages: List of {role, content} dicts.
                      Roles: "system", "user", "assistant"
            temperature: Override default temperature for this call.
                         None uses the provider default.

        Returns:
            Assistant reply as a string.

        Raises:
            AppError: If Bedrock returns no content blocks, or the response
                was stopped for content-filter reasons.
        """
        temp = temperature if temperature is not None else self._default_temperature

        logger.info(
            "bedrock_llm_chat_started",
            extra={
                "model": self._model_id,
                "message_count": len(messages),
                "temperature": temp,
            },
        )

        anthropic_messages, system_text = self._build_anthropic_messages(messages)

        body = {
            "anthropic_version": BEDROCK_ANTHROPIC_VERSION,
            "max_tokens": self._max_output_tokens,
            "temperature": temp,
            "messages": anthropic_messages,
        }
        if system_text:
            body["system"] = system_text

        response_body = await self._call_with_retry(body)

        # Handle content-filter / safety stops
        stop_reason = response_body.get("stop_reason", "")
        content_blocks = response_body.get("content", [])

        if not content_blocks:
            logger.warning(
                "bedrock_llm_no_content",
                extra={"model": self._model_id, "stop_reason": stop_reason},
            )
            raise AppError(
                message="Bedrock returned no response — content may have been blocked",
                code="LLM_BLOCKED",
            )

        if stop_reason in ("content_filtered",):
            logger.warning(
                "bedrock_llm_content_filtered",
                extra={"model": self._model_id, "stop_reason": stop_reason},
            )
            raise AppError(
                message="Response blocked by Bedrock content filters",
                code="LLM_SAFETY_BLOCK",
            )

        # Anthropic Messages API returns content as a list of typed blocks;
        # for plain-text chat there is exactly one {"type": "text", ...} block.
        reply = "".join(
            block.get("text", "")
            for block in content_blocks
            if block.get("type") == "text"
        ).strip()

        logger.info(
            "bedrock_llm_chat_completed",
            extra={
                "model": self._model_id,
                "reply_length": len(reply),
                "stop_reason": stop_reason,
            },
        )

        return reply