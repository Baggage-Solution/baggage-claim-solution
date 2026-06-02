"""
Tests for A2VisionAgent — T-010.

A2 now calls VisionProvider.analyze_image() once per image (SceneResult).
All provider calls are mocked — no real API calls needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from backend.agents.a2_vision import A2VisionAgent, NON_BAG_ATTEMPT_LIMIT
from backend.graph.state import ClaimState
from backend.vision_provider.base import SceneResult


def make_agent() -> A2VisionAgent:
    return A2VisionAgent(vision=MagicMock())

def make_state(**kwargs) -> ClaimState:
    d = {"session_id": "test-session", "passenger_message": "my bag is damaged"}
    d.update(kwargs)
    return ClaimState(**d)

def scene(*, is_bag=True, bag_confidence=0.95, object_description="suitcase",
          damage_types=None, severity_score=0.5, damage_confidence=0.9,
          brand="Samsonite", is_luxury=False, brand_confidence=0.9,
          tag_visible=False, tag_confidence=0.0) -> SceneResult:
    return SceneResult(
        is_bag=is_bag, bag_confidence=bag_confidence, object_description=object_description,
        damage_types=damage_types if damage_types is not None else ["cracked shell"],
        severity_score=severity_score, damage_confidence=damage_confidence,
        brand=brand, is_luxury=is_luxury, brand_confidence=brand_confidence,
        tag_visible=tag_visible, tag_confidence=tag_confidence,
    )


async def test_a2_skips_with_no_images():
    agent = make_agent(); agent._vision.analyze_image = AsyncMock()
    result = await agent.handle(make_state(image_paths=[]), [])
    assert result.damage_types == [] and result.severity_score == 0.0
    agent._vision.analyze_image.assert_not_called()

async def test_a2_skips_when_only_tag_photos():
    agent = make_agent(); agent._vision.analyze_image = AsyncMock()
    result = await agent.handle(make_state(image_paths=["uploads/claim_01/tag_front.jpg"]), [])
    assert result.damage_types == [] and result.severity_score == 0.0
    agent._vision.analyze_image.assert_not_called()

async def test_a2_analyzes_single_damage_image():
    agent = make_agent()
    agent._vision.analyze_image = AsyncMock(return_value=scene(damage_types=["cracked wheel"], severity_score=0.5))
    result = await agent.handle(make_state(image_paths=["uploads/claim_01/damage_front.jpg"]), [])
    assert result.damage_types == ["cracked wheel"]
    assert result.severity_score == 0.5
    assert result.brand_detected == "Samsonite"
    assert result.is_luxury is False
    assert result.compensation_estimate_usd == 75.0
    assert result.error is None

async def test_a2_takes_max_severity_across_images():
    agent = make_agent()
    agent._vision.analyze_image = AsyncMock(side_effect=[
        scene(damage_types=["scratch"], severity_score=0.3),
        scene(damage_types=["broken wheel"], severity_score=0.8),
    ])
    result = await agent.handle(make_state(image_paths=[
        "uploads/claim_01/damage_side.jpg", "uploads/claim_01/damage_wheel.jpg"]), [])
    assert result.severity_score == 0.8
    assert result.compensation_estimate_usd == 120.0

async def test_a2_deduplicates_damage_types_across_images():
    agent = make_agent()
    agent._vision.analyze_image = AsyncMock(side_effect=[
        scene(damage_types=["cracked shell", "broken wheel"]),
        scene(damage_types=["torn handle", "cracked shell"]),
    ])
    result = await agent.handle(make_state(image_paths=[
        "uploads/claim_01/damage_1.jpg", "uploads/claim_01/damage_2.jpg"]), [])
    assert result.damage_types.count("cracked shell") == 1
    assert "broken wheel" in result.damage_types
    assert "torn handle" in result.damage_types

async def test_a2_ignores_tag_photo_in_mixed_list():
    agent = make_agent()
    agent._vision.analyze_image = AsyncMock(return_value=scene(severity_score=0.4))
    result = await agent.handle(make_state(image_paths=[
        "uploads/claim_01/damage_front.jpg", "uploads/claim_01/tag_barcode.jpg"]), [])
    assert agent._vision.analyze_image.call_count == 1

async def test_a2_sets_is_luxury_for_luxury_brand():
    agent = make_agent()
    agent._vision.analyze_image = AsyncMock(return_value=scene(
        severity_score=0.4, brand="Rimowa", is_luxury=True, brand_confidence=0.95))
    result = await agent.handle(make_state(image_paths=["uploads/claim_01/rimowa_damage.jpg"]), [])
    assert result.is_luxury is True
    assert result.brand_detected == "Rimowa"

async def test_a2_sets_re_request_on_low_confidence():
    agent = make_agent()
    agent._vision.analyze_image = AsyncMock(return_value=scene(severity_score=0.5, damage_confidence=0.2))
    result = await agent.handle(make_state(image_paths=["uploads/claim_01/blurry.jpg"]), [])
    assert result.re_request_damage is True
    assert result.severity_score == 0.0

async def test_a2_compensation_linear_scale():
    agent = make_agent()
    assert agent._calculate_compensation(0.0) == 0.0
    assert agent._calculate_compensation(0.5) == 75.0
    assert agent._calculate_compensation(1.0) == 150.0

async def test_a2_sets_error_on_provider_failure():
    agent = make_agent()
    agent._vision.analyze_image = AsyncMock(side_effect=Exception("Gemini API unavailable"))
    result = await agent.handle(make_state(image_paths=["uploads/claim_01/damage.jpg"]), [])
    # A2 in this version sets a hard state.error on provider failure.
    assert result.error is not None
    assert "A2 error" in result.error

async def test_a2_flags_non_bag_image():
    agent = make_agent()
    agent._vision.analyze_image = AsyncMock(return_value=scene(
        is_bag=False, bag_confidence=0.97, object_description="wristwatch",
        damage_types=[], severity_score=0.0))
    result = await agent.handle(make_state(image_paths=["uploads/claim_01/damage_watch.jpg"]), [])
    assert result.not_a_bag is True
    assert result.non_bag_attempts == 1
    assert result.damage_types == []
    assert result.no_damage_detected is False
    assert result.last_object_description == "wristwatch"

async def test_a2_non_bag_then_real_bag_resets_counter():
    agent = make_agent()
    agent._vision.analyze_image = AsyncMock(return_value=scene(damage_types=["cracked shell"], severity_score=0.6))
    result = await agent.handle(make_state(image_paths=["uploads/claim_01/damage_bag.jpg"], non_bag_attempts=2), [])
    assert result.not_a_bag is False
    assert result.non_bag_attempts == 0
    assert result.damage_types == ["cracked shell"]

async def test_a2_detects_tag_in_damage_photo():
    agent = make_agent()
    agent._vision.analyze_image = AsyncMock(return_value=scene(
        severity_score=0.5, tag_visible=True, tag_confidence=0.85))
    result = await agent.handle(make_state(image_paths=["uploads/claim_01/damage_with_label.jpg"]), [])
    assert result.tag_in_damage_photo is True
    assert "uploads/claim_01/damage_with_label.jpg" in result.tag_candidate_paths

async def test_a2_ignores_low_confidence_tag_in_photo():
    agent = make_agent()
    agent._vision.analyze_image = AsyncMock(return_value=scene(
        severity_score=0.5, tag_visible=True, tag_confidence=0.4))
    result = await agent.handle(make_state(image_paths=["uploads/claim_01/damage_blurry_label.jpg"]), [])
    assert result.tag_in_damage_photo is False
    assert result.tag_candidate_paths == []