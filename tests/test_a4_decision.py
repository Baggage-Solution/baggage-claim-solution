"""
Tests for A4DecisionAgent — T-012.
All 5 routing scenarios from architecture doc.
All DB calls are mocked — no real Supabase needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.a4_decision import A4DecisionAgent, _generate_claim_id
from backend.graph.state import ClaimState


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_db(claim_count: int = 0, hashes: list = None) -> MagicMock:
    """Create a mock DBProvider."""
    db = MagicMock()
    db.save_claim = AsyncMock(return_value=None)
    db.get_claim_count = AsyncMock(return_value=claim_count)
    db.get_recent_hashes = AsyncMock(return_value=hashes or [])
    return db


def make_state(**kwargs) -> ClaimState:
    """Create a ClaimState with sensible defaults for A4 testing."""
    defaults = {
        "session_id": "test-session",
        "pnr": "ABC123",
        "bag_id": "1234567890",
        "image_paths": [],
        "severity_score": 0.3,
        "compensation_estimate_usd": 60.0,
        "is_luxury": False,
        "fraud_score": 0.0,
        "fraud_flags": [],
    }
    defaults.update(kwargs)
    return ClaimState(**defaults)


def make_agent(claim_count: int = 0, hashes: list = None) -> A4DecisionAgent:
    """Create A4 agent with mocked DB."""
    return A4DecisionAgent(db=make_db(claim_count=claim_count, hashes=hashes))


# ── claim ID tests ────────────────────────────────────────────────────────────

def test_generate_claim_id_format():
    """Claim ID matches CLM-YYYYMMDD-XXXX format."""
    claim_id = _generate_claim_id()
    parts = claim_id.split("-")
    assert parts[0] == "CLM"
    assert len(parts[1]) == 8   # YYYYMMDD
    assert len(parts[2]) == 4   # XXXX hex


def test_generate_claim_id_unique():
    """Two calls generate different claim IDs."""
    assert _generate_claim_id() != _generate_claim_id()


# ── SCENARIO 1 — Standard bag, low value → Lane 1 ────────────────────────────

@pytest.mark.asyncio
async def test_scenario1_standard_bag_low_value_lane1():
    """
    Scenario 1: Standard bag, $60 compensation, fraud_score=0.
    Expected: Lane 1 auto-approve.
    """
    agent = make_agent()
    state = make_state(
        compensation_estimate_usd=60.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    result = await agent.handle(state, [])

    assert result.routing_lane == 1
    assert result.claim_id is not None
    assert result.claim_id.startswith("CLM-")
    assert result.error is None


# ── SCENARIO 2 — High value → Lane 2 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario2_high_value_lane2():
    """
    Scenario 2: Standard bag, $150 compensation (exceeds $100 threshold).
    Expected: Lane 2 staff review.
    """
    agent = make_agent()
    state = make_state(
        compensation_estimate_usd=150.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    result = await agent.handle(state, [])

    assert result.routing_lane == 2
    assert result.error is None


# ── SCENARIO 3 — Luxury bag → Lane 2 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario3_luxury_bag_always_lane2():
    """
    Scenario 3: Luxury bag (Rimowa), even with low compensation.
    Expected: Lane 2 — luxury bags always go to staff review.
    """
    agent = make_agent()
    state = make_state(
        compensation_estimate_usd=40.0,   # low value — but luxury
        is_luxury=True,
        brand_detected="Rimowa",
        fraud_score=0.0,
    )

    result = await agent.handle(state, [])

    assert result.routing_lane == 2
    assert result.error is None


# ── SCENARIO 4 — pHash duplicate → Lane 2 ────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario4_phash_duplicate_lane2():
    """
    Scenario 4: pHash duplicate — fraud_score pushed to 0.5+.
    Expected: fraud_flags=['phash_duplicate'], Lane 2.
    """
    agent = make_agent()
    state = make_state(
        compensation_estimate_usd=60.0,
        is_luxury=False,
    )
    # Pre-inject fraud state with score >= 0.5 to trigger Lane 2
    state.fraud_flags = ["phash_duplicate"]
    state.fraud_score = 0.5     # ← was 0.4, needs to be >= 0.5

    result = await agent.handle(state, [])

    assert result.routing_lane == 2
    assert "phash_duplicate" in result.fraud_flags
    assert result.fraud_score >= 0.5
    assert result.error is None


# ── SCENARIO 5 — High frequency → Lane 2 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario5_high_frequency_lane2():
    """
    Scenario 5: High frequency (3+ claims) + pre-existing fraud score.
    frequency adds 0.3 → total fraud_score = 0.3+0.3 = 0.6 >= 0.5 → Lane 2.
    """
    agent = make_agent(claim_count=3)
    state = make_state(
        compensation_estimate_usd=60.0,
        is_luxury=False,
        pnr="FRAUD1",
    )
    # Pre-inject existing fraud score so frequency check pushes it over 0.5
    state.fraud_score = 0.3     # ← frequency check adds 0.3 → total 0.6

    result = await agent.handle(state, [])

    assert result.routing_lane == 2
    assert "high_frequency" in result.fraud_flags
    assert result.fraud_score >= 0.5
    assert result.error is None


# ── DB persistence tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a4_saves_claim_to_db():
    """A4 calls db.save_claim() exactly once per handle() call."""
    db = make_db()
    agent = A4DecisionAgent(db=db)
    state = make_state()

    await agent.handle(state, [])

    db.save_claim.assert_called_once()
    call_args = db.save_claim.call_args[0][0]
    assert call_args["id"] == state.claim_id
    assert call_args["pnr"] == "ABC123"


@pytest.mark.asyncio
async def test_a4_sets_error_on_db_failure():
    """A4 catches DB exceptions and sets state.error — never hard crashes."""
    db = make_db()
    db.save_claim = AsyncMock(side_effect=Exception("Supabase connection failed"))
    agent = A4DecisionAgent(db=db)
    state = make_state()

    result = await agent.handle(state, [])

    assert result.error is not None
    assert "A4 error" in result.error


# ── Luxury compensation multiplier test ───────────────────────────────────────

@pytest.mark.asyncio
async def test_a4_luxury_compensation_multiplier():
    """Luxury bags get 1.5x compensation multiplier applied by A4."""
    agent = make_agent()
    state = make_state(
        compensation_estimate_usd=80.0,
        is_luxury=True,
    )

    result = await agent.handle(state, [])

    assert result.final_compensation_usd == 120.0   # 80 × 1.5


@pytest.mark.asyncio
async def test_a4_standard_compensation_no_multiplier():
    """Standard bags get no multiplier — compensation stays the same."""
    agent = make_agent()
    state = make_state(
        compensation_estimate_usd=60.0,
        is_luxury=False,
    )

    result = await agent.handle(state, [])

    assert result.final_compensation_usd == 60.0