"""
Tests for BedrockOCRProvider — P-003
Tests use mocked Bedrock InvokeModel responses (moto has no Bedrock backend) —
no real AWS calls in the test suite. Uses the same real fixture images as
test_ocr_provider.py (Gemini) for parity between the two providers.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from backend.ocr_provider.base import TagData
from backend.ocr_provider.bedrock_ocr import BedrockOCRProvider

TEST_MODEL_ID = "anthropic.claude-sonnet-4-20250514-v1:0"
TEST_REGION = "us-east-1"
FIXTURE_DIR = Path("tests/fixtures/bag_tags")
CLEAR_TAG_IMAGE = str(FIXTURE_DIR / "clear_tag_01.jpg")


def _mock_bedrock_response(data: dict) -> dict:
    """Build a mock matching boto3's invoke_model response shape for a
    Claude Messages API reply containing a single text content block with
    a JSON string."""
    payload = {
        "content": [{"type": "text", "text": json.dumps(data)}],
        "stop_reason": "end_turn",
    }
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(payload).encode("utf-8")
    return {"body": mock_body}


@pytest.fixture
def provider():
    """BedrockOCRProvider with a fully mocked boto3 bedrock-runtime client."""
    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        p = BedrockOCRProvider(model_id=TEST_MODEL_ID, region=TEST_REGION)
        yield p, mock_client


# ── extract_bag_tag — happy path ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_bag_tag_returns_tag_data(provider):
    """extract_bag_tag() returns a fully populated TagData for a clear tag."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "flight_number": "AI202",
            "pnr": "ABC123",
            "bag_id": "045230674234",
            "confidence": 0.95,
        }
    )

    result = await p.extract_bag_tag(CLEAR_TAG_IMAGE)

    assert isinstance(result, TagData)
    assert result.flight_number == "AI202"
    assert result.pnr == "ABC123"
    assert result.bag_id == "045230674234"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_extract_bag_tag_strips_spaces_from_bag_id(provider):
    """A bag_id with internal spaces (as printed on real tags) is normalised
    to a continuous digit string before validation."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "flight_number": "EK567",
            "pnr": "XYZ789",
            "bag_id": "0452 30 674234",
            "confidence": 0.9,
        }
    )

    result = await p.extract_bag_tag(CLEAR_TAG_IMAGE)

    assert result.bag_id == "045230674234"


@pytest.mark.asyncio
async def test_extract_bag_tag_uppercases_flight_number(provider):
    """A lowercase flight number from the model is normalised to uppercase."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "flight_number": "ai202",
            "pnr": "ABC123",
            "bag_id": "045230674234",
            "confidence": 0.9,
        }
    )

    result = await p.extract_bag_tag(CLEAR_TAG_IMAGE)

    assert result.flight_number == "AI202"


# ── Validation rejection tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_bag_tag_rejects_invalid_pnr_format(provider):
    """A PNR that doesn't match the 6-char alphanumeric pattern is rejected
    (set to None) rather than passed through unchecked."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "flight_number": "AI202",
            "pnr": "TOOLONGPNR123",  # invalid — not exactly 6 chars
            "bag_id": "045230674234",
            "confidence": 0.9,
        }
    )

    result = await p.extract_bag_tag(CLEAR_TAG_IMAGE)

    assert result.pnr is None


@pytest.mark.asyncio
async def test_extract_bag_tag_rejects_invalid_bag_id_format(provider):
    """A bag_id with too few digits is rejected (set to None)."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "flight_number": "AI202",
            "pnr": "ABC123",
            "bag_id": "12345",  # invalid — too short
            "confidence": 0.9,
        }
    )

    result = await p.extract_bag_tag(CLEAR_TAG_IMAGE)

    assert result.bag_id is None


@pytest.mark.asyncio
async def test_extract_bag_tag_handles_all_null_fields(provider):
    """An unreadable tag with all fields null returns a TagData with all
    Nones and zero confidence, not an exception."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {"flight_number": None, "pnr": None, "bag_id": None, "confidence": 0.0}
    )

    result = await p.extract_bag_tag(CLEAR_TAG_IMAGE)

    assert result.flight_number is None
    assert result.pnr is None
    assert result.bag_id is None
    assert result.confidence == 0.0


# ── Image / request shape tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_bag_tag_sends_base64_image_in_request_body(provider):
    """The request body sent to Bedrock includes a base64-encoded image
    content block."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "flight_number": "AI202",
            "pnr": "ABC123",
            "bag_id": "045230674234",
            "confidence": 0.9,
        }
    )

    await p.extract_bag_tag(CLEAR_TAG_IMAGE)

    body = json.loads(mock_client.invoke_model.call_args.kwargs["body"])
    content_blocks = body["messages"][0]["content"]
    image_blocks = [b for b in content_blocks if b["type"] == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["type"] == "base64"
    assert len(image_blocks[0]["source"]["data"]) > 0


@pytest.mark.asyncio
async def test_extract_bag_tag_raises_filenotfounderror_for_missing_image(provider):
    """A nonexistent image path raises FileNotFoundError, not a silent
    TagData(confidence=0.0) — the caller needs to distinguish 'bad photo
    content' from 'photo never arrived'."""
    p, mock_client = provider

    with pytest.raises(FileNotFoundError):
        await p.extract_bag_tag("tests/fixtures/bag_tags/does_not_exist.jpg")

    mock_client.invoke_model.assert_not_called()


# ── Graceful degradation on unexpected errors ───────────────────────────────────


@pytest.mark.asyncio
async def test_extract_bag_tag_returns_zero_confidence_on_invalid_json(provider):
    """An unparseable response degrades to TagData(confidence=0.0) rather
    than propagating the JSON parse error to the caller — extract_bag_tag's
    own contract (per its docstring) is to swallow unexpected errors."""
    p, mock_client = provider
    payload = {
        "content": [{"type": "text", "text": "Not valid JSON at all"}],
        "stop_reason": "end_turn",
    }
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(payload).encode("utf-8")
    mock_client.invoke_model.return_value = {"body": mock_body}

    result = await p.extract_bag_tag(CLEAR_TAG_IMAGE)

    assert result.confidence == 0.0
    assert result.flight_number is None


# ── Retry / throttling tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retries_on_throttling_exception(provider):
    """ThrottlingException triggers a retry rather than immediate failure."""
    p, mock_client = provider

    throttle_error = ClientError(
        error_response={"Error": {"Code": "ThrottlingException", "Message": "x"}},
        operation_name="InvokeModel",
    )
    mock_client.invoke_model.side_effect = [
        throttle_error,
        _mock_bedrock_response(
            {
                "flight_number": "AI202",
                "pnr": "ABC123",
                "bag_id": "045230674234",
                "confidence": 0.9,
            }
        ),
    ]

    with patch("asyncio.sleep"):
        result = await p.extract_bag_tag(CLEAR_TAG_IMAGE)

    assert result.flight_number == "AI202"
    assert mock_client.invoke_model.call_count == 2


@pytest.mark.asyncio
async def test_does_not_retry_on_non_throttling_error(provider):
    """A non-throttling ClientError still degrades gracefully to
    TagData(confidence=0.0) per extract_bag_tag's broad except clause —
    but only after exactly one attempt, not a retry loop."""
    p, mock_client = provider
    access_denied = ClientError(
        error_response={"Error": {"Code": "AccessDeniedException", "Message": "x"}},
        operation_name="InvokeModel",
    )
    mock_client.invoke_model.side_effect = access_denied

    result = await p.extract_bag_tag(CLEAR_TAG_IMAGE)

    assert result.confidence == 0.0
    assert mock_client.invoke_model.call_count == 1