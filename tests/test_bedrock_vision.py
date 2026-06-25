"""
Tests for BedrockVisionProvider — P-003
Tests use mocked Bedrock InvokeModel responses (moto has no Bedrock backend) —
no real AWS calls in the test suite. Uses the same real fixture images as
test_vision_provider.py (Gemini) for parity between the two providers.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from backend.vision_provider.base import BrandResult, DamageResult, SceneResult
from backend.vision_provider.bedrock_vision import BedrockVisionProvider

TEST_MODEL_ID = "anthropic.claude-sonnet-4-20250514-v1:0"
TEST_REGION = "us-east-1"
FIXTURE_DIR = Path("tests/fixtures/damaged")
DAMAGED_IMAGE = str(FIXTURE_DIR / "damaged_01.jpg")
LUXURY_IMAGE = str(FIXTURE_DIR / "luxury_01.jpg")


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
    """BedrockVisionProvider with a fully mocked boto3 bedrock-runtime client."""
    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        p = BedrockVisionProvider(model_id=TEST_MODEL_ID, region=TEST_REGION)
        yield p, mock_client


# ── analyze_image tests (primary method) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_image_returns_scene_result_for_damaged_bag(provider):
    """analyze_image() returns a fully populated SceneResult for a damaged bag."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "is_bag": True,
            "bag_confidence": 0.95,
            "object_description": "black hard-shell suitcase",
            "damage_types": ["cracked shell", "broken wheel"],
            "severity_score": 0.6,
            "damage_confidence": 0.9,
            "brand": None,
            "is_luxury": False,
            "brand_confidence": 0.0,
            "tag_visible": False,
            "tag_confidence": 0.0,
        }
    )

    result = await p.analyze_image(DAMAGED_IMAGE)

    assert isinstance(result, SceneResult)
    assert result.is_bag is True
    assert result.damage_types == ["cracked shell", "broken wheel"]
    assert result.severity_score == 0.6


@pytest.mark.asyncio
async def test_analyze_image_object_gate_blocks_non_bag(provider):
    """When is_bag is false, damage/brand fields are forced to neutral even
    if the model's raw response included non-zero values for them."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "is_bag": False,
            "bag_confidence": 0.9,
            "object_description": "wristwatch",
            "damage_types": ["cracked shell"],  # should be ignored
            "severity_score": 0.8,  # should be forced to 0.0
            "damage_confidence": 0.5,
            "brand": "Rolex",
            "is_luxury": True,
            "brand_confidence": 0.8,
            "tag_visible": False,
            "tag_confidence": 0.0,
        }
    )

    result = await p.analyze_image(DAMAGED_IMAGE)

    assert result.is_bag is False
    assert result.damage_types == []
    assert result.severity_score == 0.0
    assert result.brand is None
    assert result.is_luxury is False


@pytest.mark.asyncio
async def test_analyze_image_resolves_luxury_from_static_set_even_if_model_says_false(
    provider,
):
    """A known luxury brand name forces is_luxury=True even if the model's
    own is_luxury field says false — matches GeminiVisionProvider behaviour."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "is_bag": True,
            "bag_confidence": 0.95,
            "object_description": "luxury suitcase",
            "damage_types": [],
            "severity_score": 0.0,
            "damage_confidence": 0.9,
            "brand": "Rimowa",
            "is_luxury": False,  # model disagrees, static set should override
            "brand_confidence": 0.9,
            "tag_visible": False,
            "tag_confidence": 0.0,
        }
    )

    result = await p.analyze_image(LUXURY_IMAGE)

    assert result.brand == "Rimowa"
    assert result.is_luxury is True


@pytest.mark.asyncio
async def test_analyze_image_handles_null_brand_string(provider):
    """A literal string 'null' (not JSON null) for brand is treated as None,
    matching GeminiVisionProvider's defensive parsing."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "is_bag": True,
            "bag_confidence": 0.9,
            "object_description": "generic black bag",
            "damage_types": [],
            "severity_score": 0.0,
            "damage_confidence": 0.8,
            "brand": "null",
            "is_luxury": False,
            "brand_confidence": 0.0,
            "tag_visible": False,
            "tag_confidence": 0.0,
        }
    )

    result = await p.analyze_image(DAMAGED_IMAGE)

    assert result.brand is None


@pytest.mark.asyncio
async def test_analyze_image_strips_markdown_code_fences(provider):
    """Claude occasionally wraps JSON in ```json fences despite instructions
    not to — the parser must strip them before json.loads."""
    p, mock_client = provider
    raw_json = json.dumps(
        {
            "is_bag": True,
            "bag_confidence": 0.9,
            "object_description": "suitcase",
            "damage_types": [],
            "severity_score": 0.0,
            "damage_confidence": 0.8,
            "brand": None,
            "is_luxury": False,
            "brand_confidence": 0.0,
            "tag_visible": True,
            "tag_confidence": 0.85,
        }
    )
    fenced_text = f"```json\n{raw_json}\n```"
    payload = {
        "content": [{"type": "text", "text": fenced_text}],
        "stop_reason": "end_turn",
    }
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(payload).encode("utf-8")
    mock_client.invoke_model.return_value = {"body": mock_body}

    result = await p.analyze_image(DAMAGED_IMAGE)

    assert result.tag_visible is True
    assert result.tag_confidence == 0.85


@pytest.mark.asyncio
async def test_analyze_image_raises_filenotfounderror_for_missing_image(provider):
    """A nonexistent image path raises FileNotFoundError before any Bedrock
    call is attempted."""
    p, mock_client = provider

    with pytest.raises(FileNotFoundError):
        await p.analyze_image("tests/fixtures/damaged/does_not_exist.jpg")

    mock_client.invoke_model.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_image_sends_base64_image_in_request_body(provider):
    """The request body sent to Bedrock includes a base64-encoded image
    content block, not a raw file path or PIL object."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "is_bag": True,
            "bag_confidence": 0.9,
            "object_description": "bag",
            "damage_types": [],
            "severity_score": 0.0,
            "damage_confidence": 0.8,
            "brand": None,
            "is_luxury": False,
            "brand_confidence": 0.0,
            "tag_visible": False,
            "tag_confidence": 0.0,
        }
    )

    await p.analyze_image(DAMAGED_IMAGE)

    body = json.loads(mock_client.invoke_model.call_args.kwargs["body"])
    content_blocks = body["messages"][0]["content"]
    image_blocks = [b for b in content_blocks if b["type"] == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["type"] == "base64"
    assert image_blocks[0]["source"]["media_type"] in (
        "image/jpeg",
        "image/png",
        "image/webp",
    )
    assert len(image_blocks[0]["source"]["data"]) > 0


# ── Backwards-compatible analyze_damage tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_damage_returns_damage_result(provider):
    """analyze_damage() returns a properly populated DamageResult."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {
            "damage_types": ["cracked shell", "broken wheel"],
            "severity_score": 0.6,
            "confidence": 0.9,
        }
    )

    result = await p.analyze_damage(DAMAGED_IMAGE)

    assert isinstance(result, DamageResult)
    assert result.damage_types == ["cracked shell", "broken wheel"]
    assert result.severity_score == 0.6
    assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_analyze_damage_handles_intact_bag(provider):
    """An intact bag returns an empty damage_types list and severity 0.0."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {"damage_types": [], "severity_score": 0.0, "confidence": 0.95}
    )

    result = await p.analyze_damage(DAMAGED_IMAGE)

    assert result.damage_types == []
    assert result.severity_score == 0.0


# ── Backwards-compatible classify_brand tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_classify_brand_returns_brand_result(provider):
    """classify_brand() returns a properly populated BrandResult."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {"brand": "Tumi", "is_luxury": True, "confidence": 0.85}
    )

    result = await p.classify_brand(LUXURY_IMAGE)

    assert isinstance(result, BrandResult)
    assert result.brand == "Tumi"
    assert result.is_luxury is True
    assert result.confidence == 0.85


@pytest.mark.asyncio
async def test_classify_brand_returns_none_for_unbranded_bag(provider):
    """A bag with no visible branding returns brand=None, is_luxury=False."""
    p, mock_client = provider
    mock_client.invoke_model.return_value = _mock_bedrock_response(
        {"brand": None, "is_luxury": False, "confidence": 0.0}
    )

    result = await p.classify_brand(DAMAGED_IMAGE)

    assert result.brand is None
    assert result.is_luxury is False


# ── Retry / error handling tests ────────────────────────────────────────────────


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
                "is_bag": True,
                "bag_confidence": 0.9,
                "object_description": "bag",
                "damage_types": [],
                "severity_score": 0.0,
                "damage_confidence": 0.8,
                "brand": None,
                "is_luxury": False,
                "brand_confidence": 0.0,
                "tag_visible": False,
                "tag_confidence": 0.0,
            }
        ),
    ]

    with patch("asyncio.sleep"):
        result = await p.analyze_image(DAMAGED_IMAGE)

    assert result.is_bag is True
    assert mock_client.invoke_model.call_count == 2


@pytest.mark.asyncio
async def test_does_not_retry_on_non_throttling_error(provider):
    """A non-throttling ClientError propagates immediately."""
    p, mock_client = provider
    access_denied = ClientError(
        error_response={"Error": {"Code": "AccessDeniedException", "Message": "x"}},
        operation_name="InvokeModel",
    )
    mock_client.invoke_model.side_effect = access_denied

    with pytest.raises(ClientError):
        await p.analyze_image(DAMAGED_IMAGE)

    assert mock_client.invoke_model.call_count == 1


@pytest.mark.asyncio
async def test_raises_valueerror_on_invalid_json_response(provider):
    """A non-JSON text response raises ValueError rather than crashing
    with an unhandled JSONDecodeError or returning garbage data."""
    p, mock_client = provider
    payload = {
        "content": [{"type": "text", "text": "Sorry, I cannot analyze this."}],
        "stop_reason": "end_turn",
    }
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(payload).encode("utf-8")
    mock_client.invoke_model.return_value = {"body": mock_body}

    with pytest.raises(ValueError):
        await p.analyze_image(DAMAGED_IMAGE)