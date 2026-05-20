"""
Tests for GeminiVisionProvider — T-006
Tests use mocked Gemini responses — no real API calls in test suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.vision_provider.base import BrandResult, DamageResult
from backend.vision_provider.gemini_vision import GeminiVisionProvider

# ── Fixtures ─────────────────────────────────────────────────────────────────

FIXTURE_DIR = Path("tests/fixtures/damaged")


def make_provider() -> GeminiVisionProvider:
    """Create a GeminiVisionProvider with a mocked Gemini model."""
    with patch("google.generativeai.configure"), patch(
        "google.generativeai.GenerativeModel"
    ) as mock_model_cls:
        provider = GeminiVisionProvider(api_key="test-key", model="gemini-2.5-flash")
        provider._model = mock_model_cls.return_value
    return provider


def mock_gemini_response(data: dict) -> MagicMock:
    """Create a mock Gemini response returning JSON."""
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(data)
    return mock_resp


# ── analyze_damage tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_damage_returns_damage_result():
    """analyze_damage() returns a properly populated DamageResult."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "damage_types": ["cracked shell", "broken wheel"],
            "severity_score": 0.6,
            "confidence": 0.9,
        }
    )

    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.analyze_damage("fake/path/damage.jpg")

    assert isinstance(result, DamageResult)
    assert "cracked shell" in result.damage_types
    assert result.severity_score == 0.6
    assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_analyze_damage_no_damage():
    """analyze_damage() handles empty damage list correctly."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "damage_types": [],
            "severity_score": 0.0,
            "confidence": 0.95,
        }
    )

    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.analyze_damage("fake/path/clean.jpg")

    assert result.damage_types == []
    assert result.severity_score == 0.0


@pytest.mark.asyncio
async def test_analyze_damage_strips_markdown_json():
    """analyze_damage() handles Gemini wrapping JSON in markdown code blocks."""
    provider = make_provider()
    mock_resp = MagicMock()
    mock_resp.text = '```json\n{"damage_types": ["dent"], "severity_score": 0.3, "confidence": 0.8}\n```'
    provider._model.generate_content.return_value = mock_resp

    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.analyze_damage("fake/path/dented.jpg")

    assert result.severity_score == 0.3
    assert "dent" in result.damage_types


# ── classify_brand tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_brand_luxury_detected():
    """classify_brand() correctly identifies a luxury brand."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "brand": "Rimowa",
            "is_luxury": True,
            "confidence": 0.95,
        }
    )

    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.classify_brand("fake/path/rimowa.jpg")

    assert isinstance(result, BrandResult)
    assert result.brand == "Rimowa"
    assert result.is_luxury is True
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_classify_brand_standard_bag():
    """classify_brand() correctly identifies a non-luxury brand."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "brand": "Samsonite",
            "is_luxury": False,
            "confidence": 0.88,
        }
    )

    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.classify_brand("fake/path/samsonite.jpg")

    assert result.brand == "Samsonite"
    assert result.is_luxury is False


@pytest.mark.asyncio
async def test_classify_brand_luxury_set_override():
    """
    is_luxury=True if brand is in LUXURY_BRANDS set,
    even if Gemini says is_luxury=False.
    """
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "brand": "tumi",
            "is_luxury": False,  # Gemini wrong — our set overrides
            "confidence": 0.7,
        }
    )

    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.classify_brand("fake/path/tumi.jpg")

    assert result.is_luxury is True  # LUXURY_BRANDS set overrides Gemini


@pytest.mark.asyncio
async def test_classify_brand_unknown():
    """classify_brand() handles unknown/unidentifiable brand."""
    provider = make_provider()
    provider._model.generate_content.return_value = mock_gemini_response(
        {
            "brand": None,
            "is_luxury": False,
            "confidence": 0.3,
        }
    )

    with patch.object(provider, "_load_image", return_value=MagicMock()):
        result = await provider.classify_brand("fake/path/unknown.jpg")

    assert result.brand is None
    assert result.is_luxury is False


@pytest.mark.asyncio
async def test_analyze_damage_file_not_found():
    """analyze_damage() raises FileNotFoundError for missing image."""
    provider = make_provider()

    with pytest.raises(FileNotFoundError):
        await provider.analyze_damage("nonexistent/path/image.jpg")
