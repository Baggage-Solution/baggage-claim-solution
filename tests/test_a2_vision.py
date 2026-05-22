"""
Tests for A2VisionAgent — T-010.

All VisionProvider calls are mocked — no real API calls needed.
Covers: skip conditions, single image, multiple images,
luxury detection, low confidence re-request, compensation scaling,
and error handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.a2_vision import A2VisionAgent
from backend.graph.state import ClaimState
from backend.vision_provider.base import BrandResult, DamageResult

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_agent() -> A2VisionAgent:
    """A2VisionAgent with a mocked VisionProvider."""
    mock_vision = MagicMock()
    return A2VisionAgent(vision=mock_vision)


def make_state(**kwargs) -> ClaimState:
    """ClaimState with sensible defaults for A2 testing."""
    defaults = {
        "session_id": "test-session",
        "passenger_message": "my bag is damaged",
    }
    defaults.update(kwargs)
    return ClaimState(**defaults)


def damage_result(
    damage_types=None, severity_score=0.5, confidence=0.9
) -> DamageResult:
    return DamageResult(
        damage_types=damage_types or ["cracked shell"],
        severity_score=severity_score,
        confidence=confidence,
    )


def brand_result(brand="Samsonite", is_luxury=False, confidence=0.9) -> BrandResult:
    return BrandResult(brand=brand, is_luxury=is_luxury, confidence=confidence)


# ── Skip conditions ───────────────────────────────────────────────────────────


async def test_a2_skips_with_no_images():
    """No image_paths → A2 returns state unchanged, no provider calls made."""
    agent = make_agent()
    state = make_state(image_paths=[])
    result = await agent.handle(state, [])

    assert result.damage_types == []
    assert result.severity_score == 0.0
    agent._vision.analyze_damage.assert_not_called()


async def test_a2_skips_when_only_tag_photos():
    """Only tag photo in image_paths → A2 skips (A3 handles tag photos)."""
    agent = make_agent()
    state = make_state(image_paths=["uploads/claim_01/tag_front.jpg"])
    result = await agent.handle(state, [])

    assert result.damage_types == []
    assert result.severity_score == 0.0
    agent._vision.analyze_damage.assert_not_called()


# ── Single image analysis ─────────────────────────────────────────────────────


async def test_a2_analyzes_single_damage_image():
    """Single damage photo → all A2 state fields correctly populated."""
    agent = make_agent()
    agent._vision.analyze_damage = AsyncMock(
        return_value=damage_result(["cracked wheel"], severity_score=0.5)
    )
    agent._vision.classify_brand = AsyncMock(
        return_value=brand_result("Samsonite", is_luxury=False)
    )
    state = make_state(image_paths=["uploads/claim_01/damage_front.jpg"])
    result = await agent.handle(state, [])

    assert result.damage_types == ["cracked wheel"]
    assert result.severity_score == 0.5
    assert result.brand_detected == "Samsonite"
    assert result.is_luxury is False
    assert result.compensation_estimate_usd == 75.0  # 0.5 × 150
    assert result.error is None


# ── Multiple image aggregation ────────────────────────────────────────────────


async def test_a2_takes_max_severity_across_images():
    """Two damage photos → severity_score = max of both (worst damage wins)."""
    agent = make_agent()
    agent._vision.analyze_damage = AsyncMock(
        side_effect=[
            damage_result(["scratch"], severity_score=0.3),
            damage_result(["broken wheel"], severity_score=0.8),
        ]
    )
    agent._vision.classify_brand = AsyncMock(return_value=brand_result())
    state = make_state(
        image_paths=[
            "uploads/claim_01/damage_side.jpg",
            "uploads/claim_01/damage_wheel.jpg",
        ]
    )
    result = await agent.handle(state, [])

    assert result.severity_score == 0.8
    assert result.compensation_estimate_usd == 120.0  # 0.8 × 150


async def test_a2_deduplicates_damage_types_across_images():
    """Same damage type in two images appears only once in state.damage_types."""
    agent = make_agent()
    agent._vision.analyze_damage = AsyncMock(
        side_effect=[
            damage_result(["cracked shell", "broken wheel"]),
            damage_result(["torn handle", "cracked shell"]),  # cracked shell duplicate
        ]
    )
    agent._vision.classify_brand = AsyncMock(return_value=brand_result())
    state = make_state(
        image_paths=[
            "uploads/claim_01/damage_1.jpg",
            "uploads/claim_01/damage_2.jpg",
        ]
    )
    result = await agent.handle(state, [])

    assert result.damage_types.count("cracked shell") == 1
    assert "broken wheel" in result.damage_types
    assert "torn handle" in result.damage_types


async def test_a2_ignores_tag_photo_in_mixed_list():
    """Mixed damage + tag paths → A2 only processes damage photos."""
    agent = make_agent()
    agent._vision.analyze_damage = AsyncMock(
        return_value=damage_result(severity_score=0.4)
    )
    agent._vision.classify_brand = AsyncMock(return_value=brand_result())
    state = make_state(
        image_paths=[
            "uploads/claim_01/damage_front.jpg",
            "uploads/claim_01/tag_barcode.jpg",  # must be ignored by A2
        ]
    )
    result = await agent.handle(state, [])

    assert agent._vision.analyze_damage.call_count == 1  # only damage photo


# ── Luxury detection ──────────────────────────────────────────────────────────


async def test_a2_sets_is_luxury_for_luxury_brand():
    """Rimowa detected → is_luxury=True, A4 will route Lane 2."""
    agent = make_agent()
    agent._vision.analyze_damage = AsyncMock(
        return_value=damage_result(severity_score=0.4)
    )
    agent._vision.classify_brand = AsyncMock(
        return_value=brand_result("Rimowa", is_luxury=True, confidence=0.95)
    )
    state = make_state(image_paths=["uploads/claim_01/rimowa_damage.jpg"])
    result = await agent.handle(state, [])

    assert result.is_luxury is True
    assert result.brand_detected == "Rimowa"


# ── Re-request logic ──────────────────────────────────────────────────────────


async def test_a2_sets_re_request_on_low_confidence():
    """Confidence below threshold → re_request_damage=True, state not updated."""
    agent = make_agent()
    agent._vision.analyze_damage = AsyncMock(
        return_value=damage_result(severity_score=0.5, confidence=0.2)  # below 0.4
    )
    state = make_state(image_paths=["uploads/claim_01/blurry.jpg"])
    result = await agent.handle(state, [])

    assert result.re_request_damage is True
    assert result.severity_score == 0.0  # not set — image rejected


# ── Compensation calculation ──────────────────────────────────────────────────


async def test_a2_compensation_linear_scale():
    """Compensation = severity × 150 across the full scale."""
    agent = make_agent()
    assert agent._calculate_compensation(0.0) == 0.0
    assert agent._calculate_compensation(0.5) == 75.0
    assert agent._calculate_compensation(1.0) == 150.0


# ── Error handling ────────────────────────────────────────────────────────────


async def test_a2_sets_error_on_provider_failure():
    """VisionProvider raises → state.error set, pipeline never crashes."""
    agent = make_agent()
    agent._vision.analyze_damage = AsyncMock(
        side_effect=Exception("Gemini API unavailable")
    )
    state = make_state(image_paths=["uploads/claim_01/damage.jpg"])
    result = await agent.handle(state, [])

    assert result.error is not None
    assert "A2 error" in result.error
