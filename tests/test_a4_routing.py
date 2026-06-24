"""
Unit tests for A4DecisionAgent routing logic — T-020.

Focused exclusively on the 5 routing scenarios from the architecture doc.
Complements the broader test_a4_decision.py (T-012) which also covers
claim-ID format, DB persistence, and error handling.

All DB calls are mocked — no real Supabase needed.
No Gemini/vision/OCR calls — pure routing logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.a4_decision import A4DecisionAgent
from backend.graph.state import ClaimState

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_db(claim_count: int = 0, hashes: list | None = None) -> MagicMock:
    """Mock DBProvider with configurable claim count and stored hashes."""
    db = MagicMock()
    db.save_claim = AsyncMock(return_value=None)
    db.get_claim_count = AsyncMock(return_value=claim_count)
    db.get_recent_hashes = AsyncMock(return_value=hashes or [])
    return db


def make_state(**kwargs) -> ClaimState:
    """
    ClaimState with image_paths pre-set so A4 guard passes.
    Includes both a damage image and a tag image — the minimal complete set.
    """
    defaults = {
        "session_id": "test-a4-routing",
        "passenger_message": "confirm",
        "pnr": "ABC123",
        "bag_id": "1234567890",
        "flight_number": "AI202",
        "image_paths": [
            "uploads/test/damage_front.jpg",
            "uploads/test/bag_tag.jpg",
        ],
        "severity_score": 0.3,
        "compensation_estimate_usd": 60.0,
        "is_luxury": False,
        "fraud_score": 0.0,
        "fraud_flags": [],
    }
    defaults.update(kwargs)
    return ClaimState(**defaults)


# ── SCENARIO 1 ─────────────────────────────────────────────────────────────────
# Standard bag, low value, no fraud → Lane 1 auto-approve


@pytest.mark.asyncio
async def test_routing_scenario1_lane1_auto_approve():
    """
    Scenario 1: Standard bag, $60 compensation, fraud_score=0, non-luxury.
    A4 must route to Lane 1 (auto-approve).
    """
    agent = A4DecisionAgent(db=make_db())
    state = make_state(
        compensation_estimate_usd=60.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    result = await agent.handle(state, [])

    assert result.routing_lane == 1, "Standard $60 non-luxury bag must route to Lane 1"
    assert result.claim_id is not None
    assert result.error is None


@pytest.mark.asyncio
async def test_routing_scenario1_at_threshold_still_lane1():
    """$100 compensation (exactly at threshold) must still be Lane 1."""
    agent = A4DecisionAgent(db=make_db())
    state = make_state(
        compensation_estimate_usd=100.0, is_luxury=False, fraud_score=0.0
    )

    result = await agent.handle(state, [])

    assert result.routing_lane == 1


# ── SCENARIO 2 ─────────────────────────────────────────────────────────────────
# High value → Lane 2 staff review


@pytest.mark.asyncio
async def test_routing_scenario2_high_value_lane2():
    """
    Scenario 2: $150 compensation (above $100 threshold).
    A4 must route to Lane 2 (staff review).
    """
    agent = A4DecisionAgent(db=make_db())
    state = make_state(
        compensation_estimate_usd=150.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    result = await agent.handle(state, [])

    assert result.routing_lane == 2, "High-value claim ($150) must route to Lane 2"
    assert result.error is None


@pytest.mark.asyncio
async def test_routing_scenario2_just_above_threshold_is_lane2():
    """$100.01 compensation is above threshold → Lane 2."""
    agent = A4DecisionAgent(db=make_db())
    state = make_state(
        compensation_estimate_usd=100.01, is_luxury=False, fraud_score=0.0
    )

    result = await agent.handle(state, [])

    assert result.routing_lane == 2


# ── SCENARIO 3 ─────────────────────────────────────────────────────────────────
# Luxury bag → always Lane 2


@pytest.mark.asyncio
async def test_routing_scenario3_luxury_bag_always_lane2():
    """
    Scenario 3: Luxury bag (Rimowa), even with low compensation ($40).
    Luxury bags must ALWAYS route to Lane 2 regardless of compensation.
    """
    agent = A4DecisionAgent(db=make_db())
    state = make_state(
        compensation_estimate_usd=40.0,
        is_luxury=True,
        brand_detected="Rimowa",
        fraud_score=0.0,
    )

    result = await agent.handle(state, [])

    assert result.routing_lane == 2, "Luxury bags must always route to Lane 2"
    assert result.error is None


@pytest.mark.asyncio
async def test_routing_scenario3_luxury_low_fraud_still_lane2():
    """Luxury + zero fraud + $1 compensation → still Lane 2. Luxury overrides all."""
    agent = A4DecisionAgent(db=make_db())
    state = make_state(
        compensation_estimate_usd=1.0,
        is_luxury=True,
        brand_detected="Louis Vuitton",
        fraud_score=0.0,
    )

    result = await agent.handle(state, [])

    assert result.routing_lane == 2


@pytest.mark.asyncio
async def test_routing_scenario3_luxury_compensation_multiplier_applied():
    """
    Luxury bags get 1.5x compensation multiplier by A4.
    $80 estimate × 1.5 = $120 final.
    """
    agent = A4DecisionAgent(db=make_db())
    state = make_state(
        compensation_estimate_usd=80.0,
        is_luxury=True,
    )

    result = await agent.handle(state, [])

    assert result.final_compensation_usd == 120.0, "Luxury multiplier must be 1.5×"
    assert result.routing_lane == 2


# ── SCENARIO 4 ─────────────────────────────────────────────────────────────────
# pHash duplicate → Lane 2


@pytest.mark.asyncio
async def test_routing_scenario4_phash_duplicate_lane2():
    """
    Scenario 4: pHash duplicate — fraud_score pre-set at 0.5.
    A4 routes to Lane 2 (fraud_score >= 0.5 blocks Lane 1 eligibility).
    """
    agent = A4DecisionAgent(db=make_db())
    state = make_state(
        compensation_estimate_usd=60.0,
        is_luxury=False,
    )
    state.fraud_flags = ["phash_duplicate"]
    state.fraud_score = 0.5

    result = await agent.handle(state, [])

    assert result.routing_lane == 2, "pHash duplicate flag must trigger Lane 2"
    assert "phash_duplicate" in result.fraud_flags
    assert result.fraud_score >= 0.5
    assert result.error is None


@pytest.mark.asyncio
async def test_routing_scenario4_fraud_flag_preserved_in_output():
    """Fraud flags set before A4 are preserved in output state."""
    agent = A4DecisionAgent(db=make_db())
    state = make_state(fraud_score=0.5)
    state.fraud_flags = ["phash_duplicate"]

    result = await agent.handle(state, [])

    assert "phash_duplicate" in result.fraud_flags


# ── SCENARIO 5 ─────────────────────────────────────────────────────────────────
# High claim frequency → Lane 2


@pytest.mark.asyncio
async def test_routing_scenario5_high_frequency_lane2():
    """
    Scenario 5: High frequency (3 existing claims in last 30 days).
    Frequency check adds 0.3 to fraud_score.
    Pre-seeding state.fraud_score=0.3 → frequency pushes total to 0.6 → Lane 2.
    """
    agent = A4DecisionAgent(db=make_db(claim_count=3))
    state = make_state(
        pnr="FRAUD1",
        compensation_estimate_usd=60.0,
        is_luxury=False,
    )
    state.fraud_score = 0.3  # frequency check will add 0.3 → 0.6

    result = await agent.handle(state, [])

    assert result.routing_lane == 2, "High-frequency PNR must trigger Lane 2"
    assert "high_frequency" in result.fraud_flags
    assert result.fraud_score >= 0.5
    assert result.error is None


@pytest.mark.asyncio
async def test_routing_scenario5_low_frequency_no_flag():
    """Claim count below threshold (1 claim) → no high_frequency flag."""
    agent = A4DecisionAgent(db=make_db(claim_count=1))
    state = make_state(pnr="CLEAN1", compensation_estimate_usd=60.0, is_luxury=False)

    result = await agent.handle(state, [])

    assert "high_frequency" not in result.fraud_flags


# ── Guard: no routing when images are incomplete ──────────────────────────────


@pytest.mark.asyncio
async def test_a4_skips_when_no_tag_image_and_no_tag_data():
    """
    A4 guard: if only damage images are present (no tag and no tag_data_complete),
    A4 must skip — routing_lane stays None.
    """
    agent = A4DecisionAgent(db=make_db())
    state = ClaimState(
        session_id="test-guard",
        passenger_message="here are my damage photos",
        image_paths=["uploads/test/damage_front.jpg"],  # no tag image
        pnr=None,
        bag_id=None,
        tag_data_complete=False,
    )

    result = await agent.handle(state, [])

    assert result.routing_lane is None


@pytest.mark.asyncio
async def test_a4_skips_when_re_request_tag_is_set():
    """
    A4 guard: re_request_tag=True (blurry tag) blocks routing.
    routing_lane must remain None.
    """
    agent = A4DecisionAgent(db=make_db())
    state = make_state(re_request_tag=True)

    result = await agent.handle(state, [])

    assert result.routing_lane is None


@pytest.mark.asyncio
async def test_a4_skips_when_re_request_damage_is_set():
    """
    A4 guard: re_request_damage=True (blurry damage photos) blocks routing.
    routing_lane must remain None.
    """
    agent = A4DecisionAgent(db=make_db())
    state = make_state(re_request_damage=True)

    result = await agent.handle(state, [])

    assert result.routing_lane is None


# ── Standard compensation (no multiplier) ────────────────────────────────────


@pytest.mark.asyncio
async def test_routing_standard_bag_compensation_no_multiplier():
    """Standard (non-luxury) bag: final_compensation_usd == compensation_estimate_usd."""
    agent = A4DecisionAgent(db=make_db())
    state = make_state(compensation_estimate_usd=60.0, is_luxury=False)

    result = await agent.handle(state, [])

    assert result.final_compensation_usd == 60.0
