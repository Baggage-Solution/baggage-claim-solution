"""
Tests for A3OCRAgent — T-011.

All OCRProvider calls are mocked — no real API calls needed.
Covers: skip conditions, full extraction, confidence threshold,
partial data (null fields), multi-tag filtering, and error handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.a3_ocr import A3OCRAgent
from backend.graph.state import ClaimState
from backend.ocr_provider.base import TagData

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_agent() -> A3OCRAgent:
    """A3OCRAgent with a mocked OCRProvider."""
    mock_ocr = MagicMock()
    return A3OCRAgent(ocr=mock_ocr)


def make_state(**kwargs) -> ClaimState:
    """ClaimState with sensible defaults for A3 testing."""
    defaults = {
        "session_id": "test-session",
        "passenger_message": "my bag is damaged",
    }
    defaults.update(kwargs)
    return ClaimState(**defaults)


def tag_data(
    flight_number="AI202",
    pnr="ABC123",
    bag_id="0572351234",
    confidence=0.95,
) -> TagData:
    return TagData(
        flight_number=flight_number,
        pnr=pnr,
        bag_id=bag_id,
        confidence=confidence,
    )


# ── Skip conditions ───────────────────────────────────────────────────────────


async def test_a3_skips_with_no_images():
    """No image_paths at all → A3 returns state unchanged, no provider call."""
    agent = make_agent()
    state = make_state(image_paths=[])
    result = await agent.handle(state, [])

    assert result.pnr is None
    assert result.flight_number is None
    agent._ocr.extract_bag_tag.assert_not_called()


async def test_a3_skips_when_only_damage_photos():
    """Only damage photos → A3 skips (A2 handles those, A3 needs tag photo)."""
    agent = make_agent()
    state = make_state(image_paths=["uploads/claim_01/damage_front.jpg"])
    result = await agent.handle(state, [])

    assert result.pnr is None
    assert result.ocr_confidence == 0.0
    agent._ocr.extract_bag_tag.assert_not_called()


# ── Successful extraction ─────────────────────────────────────────────────────


async def test_a3_extracts_all_fields_successfully():
    """Tag photo present → all fields written to state correctly."""
    agent = make_agent()
    agent._ocr.extract_bag_tag = AsyncMock(
        return_value=tag_data("AI202", "ABC123", "0572351234", 0.95)
    )
    state = make_state(image_paths=["uploads/claim_01/tag_front.jpg"])
    result = await agent.handle(state, [])

    assert result.flight_number == "AI202"
    assert result.pnr == "ABC123"
    assert result.bag_id == "0572351234"
    assert result.ocr_confidence == 0.95
    assert result.re_request_tag is False
    assert result.error is None


async def test_a3_uses_first_tag_image_only():
    """Multiple tag images → only the first one sent to provider."""
    agent = make_agent()
    agent._ocr.extract_bag_tag = AsyncMock(return_value=tag_data())
    state = make_state(
        image_paths=[
            "uploads/claim_01/tag_front.jpg",
            "uploads/claim_01/tag_back.jpg",
        ]
    )
    await agent.handle(state, [])

    assert agent._ocr.extract_bag_tag.call_count == 1
    called_with = agent._ocr.extract_bag_tag.call_args[0][0]
    assert called_with == "uploads/claim_01/tag_front.jpg"


async def test_a3_processes_tag_not_damage_in_mixed_list():
    """Mixed damage + tag images → A3 only passes tag image to provider."""
    agent = make_agent()
    agent._ocr.extract_bag_tag = AsyncMock(return_value=tag_data())
    state = make_state(
        image_paths=[
            "uploads/claim_01/damage_front.jpg",  # A2's job
            "uploads/claim_01/tag_barcode.jpg",  # A3's job
        ]
    )
    await agent.handle(state, [])

    assert agent._ocr.extract_bag_tag.call_count == 1
    called_with = agent._ocr.extract_bag_tag.call_args[0][0]
    assert "tag" in called_with


# ── Confidence threshold ──────────────────────────────────────────────────────


async def test_a3_sets_re_request_on_low_confidence():
    """Confidence below 0.7 → re_request_tag=True, fields NOT written."""
    agent = make_agent()
    agent._ocr.extract_bag_tag = AsyncMock(
        return_value=tag_data("AI202", "ABC123", "0572351234", confidence=0.5)
    )
    state = make_state(image_paths=["uploads/claim_01/blurry_tag.jpg"])
    result = await agent.handle(state, [])

    assert result.re_request_tag is True
    assert result.ocr_confidence == 0.5  # confidence still written
    assert result.pnr is None  # fields NOT written on low confidence
    assert result.bag_id is None


async def test_a3_accepts_exactly_at_confidence_threshold():
    """Confidence exactly at 0.7 → accepted (threshold is strictly less than)."""
    agent = make_agent()
    agent._ocr.extract_bag_tag = AsyncMock(return_value=tag_data(confidence=0.7))
    state = make_state(image_paths=["uploads/claim_01/tag_ok.jpg"])
    result = await agent.handle(state, [])

    assert result.re_request_tag is False
    assert result.pnr is not None


# ── Partial data (null fields from provider) ──────────────────────────────────


async def test_a3_handles_null_pnr_gracefully():
    """Provider returns None PNR (not on this tag type) → state.pnr = None, no crash."""
    agent = make_agent()
    agent._ocr.extract_bag_tag = AsyncMock(
        return_value=tag_data(pnr=None, confidence=0.9)
    )
    state = make_state(image_paths=["uploads/claim_01/tag_no_pnr.jpg"])
    result = await agent.handle(state, [])

    assert result.pnr is None  # correctly propagated
    assert result.flight_number == "AI202"  # other fields still written
    assert result.error is None


async def test_a3_handles_null_bag_id_gracefully():
    """Provider returns None bag_id → state.bag_id = None, no crash."""
    agent = make_agent()
    agent._ocr.extract_bag_tag = AsyncMock(
        return_value=tag_data(bag_id=None, confidence=0.88)
    )
    state = make_state(image_paths=["uploads/claim_01/tag_partial.jpg"])
    result = await agent.handle(state, [])

    assert result.bag_id is None
    assert result.error is None


# ── Error handling ────────────────────────────────────────────────────────────


async def test_a3_sets_error_on_provider_failure():
    """OCRProvider raises → state.error set, pipeline never crashes."""
    agent = make_agent()
    agent._ocr.extract_bag_tag = AsyncMock(
        side_effect=Exception("OCR service unavailable")
    )
    state = make_state(image_paths=["uploads/claim_01/tag_front.jpg"])
    result = await agent.handle(state, [])

    assert result.error is not None
    assert "A3 error" in result.error
