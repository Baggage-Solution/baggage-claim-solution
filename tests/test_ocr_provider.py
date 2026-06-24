"""
Tests for GeminiOCRProvider — T-007.

All Gemini API calls are mocked — no real API calls, no API key needed.
Follows the same structure as test_vision_provider.py (T-006).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.ocr_provider.base import TagData
from backend.ocr_provider.gemini_ocr import GeminiOCRProvider

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_provider() -> GeminiOCRProvider:
    """GeminiOCRProvider with a mocked Gemini model — no API key needed."""
    from unittest.mock import AsyncMock

    with patch("google.generativeai.configure"), patch(
        "google.generativeai.GenerativeModel"
    ) as mock_cls:
        provider = GeminiOCRProvider(api_key="test-key", model="gemini-2.5-flash")
        provider._model = mock_cls.return_value
    # Provider now uses generate_content_async — delegate to generate_content.return_value.
    provider._model.generate_content_async = AsyncMock(
        side_effect=lambda *a, **kw: provider._model.generate_content.return_value
    )
    return provider


def mock_gemini_response(data: dict) -> MagicMock:
    """Build a mock Gemini response returning JSON."""
    resp = MagicMock()
    resp.text = json.dumps(data)
    return resp


def mock_gemini_raw(text: str) -> MagicMock:
    """Build a mock Gemini response with raw text (for markdown-strip tests)."""
    resp = MagicMock()
    resp.text = text
    return resp


# ── extract_bag_tag — success cases ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_bag_tag_success():
    """All fields extracted and validated correctly from a clean bag tag."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "flight_number": "AI202",
            "pnr": "ABC123",
            "bag_id": "0572351234",
            "confidence": 0.95,
        }
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")

    assert result.flight_number == "AI202"
    assert result.pnr == "ABC123"
    assert result.bag_id == "0572351234"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_extract_bag_tag_markdown_stripped():
    """Gemini wraps JSON in ```json — _parse_json_response strips it cleanly."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_raw(
        '```json\n{"flight_number": "EK567", "pnr": "XY1234", '
        '"bag_id": "9876543210", "confidence": 0.88}\n```'
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")

    assert result.flight_number == "EK567"
    assert result.pnr == "XY1234"
    assert result.bag_id == "9876543210"
    assert result.confidence == 0.88


@pytest.mark.asyncio
async def test_extract_bag_tag_lowercase_normalised():
    """Gemini returns lowercase flight/PNR → provider normalises to uppercase."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "flight_number": "ai202",
            "pnr": "abc123",
            "bag_id": "1234567890",
            "confidence": 0.80,
        }
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")

    assert result.flight_number == "AI202"
    assert result.pnr == "ABC123"


@pytest.mark.asyncio
async def test_extract_bag_tag_low_confidence():
    """Blurry tag — confidence < 0.7 returned so A3 sets re_request_tag = True."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "flight_number": "AI202",
            "pnr": "ABC123",
            "bag_id": "0572351234",
            "confidence": 0.45,
        }
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")

    assert result.confidence == 0.45
    assert result.confidence < 0.7  # A3 checks this threshold


@pytest.mark.asyncio
async def test_extract_bag_tag_spaces_stripped_from_bag_id():
    """
    Real-world tags print bag ID with spaces e.g. "0452 30 674234".
    Provider strips spaces → "045230674234" passes \d{10,12} validation.
    This was the fix for the smoke test failure on the Swissport SAW tag.
    """
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "flight_number": None,
            "pnr": None,
            "bag_id": "0452 30 674234",  # exactly as Gemini reads it from the tag
            "confidence": 1.0,
        }
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")

    assert result.bag_id == "045230674234"  # spaces stripped, digits preserved
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_extract_bag_tag_12_digit_bag_id():
    """12-digit bag IDs (some airlines) pass validation after T-007 fix."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "flight_number": "TK1234",
            "pnr": None,
            "bag_id": "045230674234",
            "confidence": 0.92,
        }
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")

    assert result.bag_id == "045230674234"
    assert len(result.bag_id) == 12


# ── PNR validation ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_pnr_too_short():
    """PNR with only 4 chars fails [A-Z0-9]{6} validation → None."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "flight_number": "AI202",
            "pnr": "AB12",
            "bag_id": "1234567890",
            "confidence": 0.80,
        }
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")
    assert result.pnr is None


@pytest.mark.asyncio
async def test_invalid_pnr_special_characters():
    """PNR with hyphen fails validation → None."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "flight_number": "AI202",
            "pnr": "AB-123",
            "bag_id": "1234567890",
            "confidence": 0.80,
        }
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")
    assert result.pnr is None


@pytest.mark.asyncio
async def test_null_pnr_from_gemini():
    """Gemini returns null PNR (not all tags have PNR) → None in TagData."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "flight_number": "AI202",
            "pnr": None,
            "bag_id": "1234567890",
            "confidence": 0.50,
        }
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")
    assert result.pnr is None


# ── Bag ID validation ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_bag_id_too_short():
    """Bag ID with 9 digits fails validation → None."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "flight_number": "AI202",
            "pnr": "ABC123",
            "bag_id": "123456789",
            "confidence": 0.80,
        }
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")
    assert result.bag_id is None


@pytest.mark.asyncio
async def test_invalid_bag_id_contains_letters():
    """Bag ID with letters fails validation → None."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "flight_number": "AI202",
            "pnr": "ABC123",
            "bag_id": "12345ABCDE",
            "confidence": 0.80,
        }
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")
    assert result.bag_id is None


# ── Error handling ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_not_found_raises():
    """Non-existent image path raises FileNotFoundError — not swallowed."""
    provider = make_provider()
    with pytest.raises(FileNotFoundError):
        await provider.extract_bag_tag("/nonexistent/path/tag.jpg")


@pytest.mark.asyncio
async def test_gemini_api_failure_returns_safe_tagdata():
    """Gemini API exception → returns TagData(confidence=0.0) instead of crashing."""
    provider = make_provider()
    provider._model.generate_content.side_effect = Exception("Gemini API unavailable")
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")

    assert isinstance(result, TagData)
    assert result.confidence == 0.0
    assert result.pnr is None
    assert result.bag_id is None


@pytest.mark.asyncio
async def test_malformed_json_returns_safe_tagdata():
    """Gemini returns freetext instead of JSON → TagData(confidence=0.0) safely."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_raw(
        "I cannot read this image clearly."
    )
    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.extract_bag_tag("fake/tag.jpg")

    assert isinstance(result, TagData)
    assert result.confidence == 0.0
