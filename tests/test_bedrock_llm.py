from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from backend.core.exceptions import AppError
from backend.llm_provider.bedrock_llm import BedrockLLMProvider

TEST_MODEL_ID = "anthropic.claude-sonnet-4-20250514-v1:0"
TEST_REGION = "us-east-1"


def _mock_bedrock_response(text: str, stop_reason: str = "end_turn") -> MagicMock:
    """Build a MagicMock matching boto3's invoke_model response shape.

    Bedrock's InvokeModel returns {"body": StreamingBody} where the body
    is a file-like object whose .read() yields the raw JSON bytes — this
    mirrors that exactly so the provider's json.loads(response["body"].read())
    call works unmodified against the mock.
    """
    payload = {
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
    }
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(payload).encode("utf-8")
    return {"body": mock_body}


@pytest.fixture
def provider():
    """BedrockLLMProvider with a fully mocked boto3 bedrock-runtime client.

    moto does not support Bedrock (confirmed — only S3/SQS/Secrets Manager/
    etc. have moto backends), so unittest.mock.patch is used here instead,
    exactly as flagged in the P-003 task notes.
    """
    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        p = BedrockLLMProvider(model_id=TEST_MODEL_ID, region=TEST_REGION)
        yield p, mock_client


@pytest.mark.asyncio
async def test_chat_returns_text_from_response(provider):
    """chat() extracts and returns the text content block from a normal reply."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response("Hello there!")

    reply = await p.chat([{"role": "user", "content": "Hi"}])

    assert reply == "Hello there!"


@pytest.mark.asyncio
async def test_chat_calls_invoke_model_with_correct_model_id(provider):
    """The configured model_id is passed through to invoke_model, never
    hardcoded inside the provider."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response("ok")

    await p.chat([{"role": "user", "content": "Hi"}])

    call_kwargs = mock_client.invoke_model.call_args.kwargs
    assert call_kwargs["modelId"] == TEST_MODEL_ID


@pytest.mark.asyncio
async def test_chat_sends_anthropic_version_and_max_tokens(provider):
    """Request body includes the Bedrock-required anthropic_version field
    and respects the configured max_output_tokens."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response("ok")

    await p.chat([{"role": "user", "content": "Hi"}])

    body = json.loads(mock_client.invoke_model.call_args.kwargs["body"])
    assert body["anthropic_version"] == "bedrock-2023-05-31"
    assert body["max_tokens"] == 1024


@pytest.mark.asyncio
async def test_chat_extracts_system_message_to_top_level_field(provider):
    """A 'system' role message is NOT included in the messages array —
    Anthropic's API requires it as a separate top-level 'system' field."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response("ok")

    await p.chat(
        [
            {"role": "system", "content": "You are a helpful airline assistant."},
            {"role": "user", "content": "Hi"},
        ]
    )

    body = json.loads(mock_client.invoke_model.call_args.kwargs["body"])
    assert body["system"] == "You are a helpful airline assistant."
    assert all(m["role"] != "system" for m in body["messages"])
    assert len(body["messages"]) == 1


@pytest.mark.asyncio
async def test_chat_preserves_assistant_role_name(provider):
    """Unlike Gemini (which renames 'assistant' to 'model'), Anthropic's
    Messages API uses 'assistant' directly — no role renaming needed."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response("ok")

    await p.chat(
        [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
        ]
    )

    body = json.loads(mock_client.invoke_model.call_args.kwargs["body"])
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "assistant", "user"]


@pytest.mark.asyncio
async def test_chat_respects_temperature_override(provider):
    """An explicit temperature argument overrides the provider default."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response("ok")

    await p.chat([{"role": "user", "content": "Hi"}], temperature=0.9)

    body = json.loads(mock_client.invoke_model.call_args.kwargs["body"])
    assert body["temperature"] == 0.9


@pytest.mark.asyncio
async def test_chat_uses_default_temperature_when_not_overridden(provider):
    """Without an override, the provider's constructor-supplied default is used."""
    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        p = BedrockLLMProvider(
            model_id=TEST_MODEL_ID, region=TEST_REGION, temperature=0.5
        )
        mock_client.invoke_model.return_value = _mock_bedrock_response("ok")

        await p.chat([{"role": "user", "content": "Hi"}])

        body = json.loads(mock_client.invoke_model.call_args.kwargs["body"])
        assert body["temperature"] == 0.5


@pytest.mark.asyncio
async def test_chat_raises_apperror_on_empty_content(provider):
    """An empty content list (e.g. fully content-filtered response) raises
    AppError rather than returning a silent empty string — matches
    GeminiLLMProvider's behaviour on safety blocks."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = {
        "body": BytesIO(
            json.dumps({"content": [], "stop_reason": "content_filtered"}).encode()
        )
    }

    with pytest.raises(AppError) as exc_info:
        await p.chat([{"role": "user", "content": "Hi"}])

    assert exc_info.value.code == "LLM_BLOCKED"


@pytest.mark.asyncio
async def test_chat_raises_apperror_on_content_filtered_stop_reason(provider):
    """A non-empty content list with stop_reason='content_filtered' still
    raises AppError — content may be partial/unsafe even if not empty."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        "partial", stop_reason="content_filtered"
    )

    with pytest.raises(AppError) as exc_info:
        await p.chat([{"role": "user", "content": "Hi"}])

    assert exc_info.value.code == "LLM_SAFETY_BLOCK"


@pytest.mark.asyncio
async def test_chat_retries_on_throttling_exception(provider):
    """ThrottlingException triggers a retry rather than an immediate failure."""
    p, mock_client = provider

    throttle_error = ClientError(
        error_response={"Error": {"Code": "ThrottlingException", "Message": "x"}},
        operation_name="InvokeModel",
    )
    mock_client.invoke_model.side_effect = [
        throttle_error,
        _mock_bedrock_response("recovered after retry"),
    ]

    with patch("asyncio.sleep") as mock_sleep:  # skip the real 30s wait in tests
        reply = await p.chat([{"role": "user", "content": "Hi"}])

    assert reply == "recovered after retry"
    assert mock_client.invoke_model.call_count == 2
    mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_chat_does_not_retry_on_non_throttling_error(provider):
    """A non-throttling ClientError (e.g. AccessDeniedException) propagates
    immediately — retrying a permissions error wastes 30-90s for nothing."""
    p, mock_client = provider

    access_denied = ClientError(
        error_response={"Error": {"Code": "AccessDeniedException", "Message": "x"}},
        operation_name="InvokeModel",
    )
    mock_client.invoke_model.side_effect = access_denied

    with pytest.raises(ClientError):
        await p.chat([{"role": "user", "content": "Hi"}])

    assert mock_client.invoke_model.call_count == 1


@pytest.mark.asyncio
async def test_chat_gives_up_after_three_throttled_attempts(provider):
    """After exhausting all 3 retry attempts on persistent throttling, the
    last exception is re-raised rather than retrying forever."""
    p, mock_client = provider

    throttle_error = ClientError(
        error_response={"Error": {"Code": "ThrottlingException", "Message": "x"}},
        operation_name="InvokeModel",
    )
    mock_client.invoke_model.side_effect = [throttle_error] * 3

    with patch("asyncio.sleep"):
        with pytest.raises(ClientError):
            await p.chat([{"role": "user", "content": "Hi"}])

    assert mock_client.invoke_model.call_count == 3