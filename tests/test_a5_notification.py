"""
Tests for A5NotificationAgent — T-015.
All DB calls and SSE pushes are mocked — no real Supabase or HTTP needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.a5_notification import (A5NotificationAgent,
                                            get_or_create_queue)
from backend.graph.state import ClaimState

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_db() -> MagicMock:
    """Create a mock DBProvider."""
    db = MagicMock()
    db.update_claim_status = AsyncMock(return_value=None)
    return db


def make_agent(db=None) -> A5NotificationAgent:
    """Create A5 agent with mocked DB."""
    return A5NotificationAgent(db=db or make_db())


def make_state(**kwargs) -> ClaimState:
    """Create a ClaimState with sensible defaults for A5 testing."""
    defaults = {
        "session_id": "test-session-a5",
        "claim_id": "CLM-20260522-TEST",
        "routing_lane": 1,
        "final_compensation_usd": 60.0,
        "fraud_score": 0.0,
    }
    defaults.update(kwargs)
    return ClaimState(**defaults)


# ── Lane 1 tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lane1_generates_voucher():
    """Lane 1: A5 generates a VCH-XXXXXXXX voucher code."""
    agent = make_agent()
    state = make_state(routing_lane=1)

    result = await agent.handle(state, [])

    assert result.voucher_code is not None
    assert result.voucher_code.startswith("VCH-")
    assert len(result.voucher_code) == 12  # VCH- + 8 chars
    assert result.error is None


@pytest.mark.asyncio
async def test_lane1_sets_notification_sent():
    """Lane 1: notification_sent is True after handle()."""
    agent = make_agent()
    state = make_state(routing_lane=1)

    result = await agent.handle(state, [])

    assert result.notification_sent is True


@pytest.mark.asyncio
async def test_lane1_updates_db_status_approved():
    """Lane 1: DB update_claim_status called with APPROVED."""
    db = make_db()
    agent = A5NotificationAgent(db=db)
    state = make_state(routing_lane=1)

    await agent.handle(state, [])

    db.update_claim_status.assert_called_once_with("CLM-20260522-TEST", "APPROVED")


@pytest.mark.asyncio
async def test_lane1_pushes_sse_event():
    """Lane 1: SSE event of type 'lane1_result' pushed to session queue."""
    agent = make_agent()
    state = make_state(routing_lane=1)

    await agent.handle(state, [])

    queue = get_or_create_queue(state.session_id)
    assert not queue.empty()
    event = await queue.get()
    assert event["type"] == "lane1_result"
    assert "voucher_code" in event
    assert event["voucher_code"].startswith("VCH-")


@pytest.mark.asyncio
async def test_lane1_sets_result_step():
    """Lane 1: conversation_step advances to 'result'."""
    agent = make_agent()
    state = make_state(routing_lane=1)

    result = await agent.handle(state, [])

    assert result.conversation_step == "result"


# ── Lane 2 tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lane2_sets_hitl_queued():
    """Lane 2: hitl_queued is True after handle()."""
    agent = make_agent()
    state = make_state(routing_lane=2)

    result = await agent.handle(state, [])

    assert result.hitl_queued is True
    assert result.error is None


@pytest.mark.asyncio
async def test_lane2_updates_db_status_awaiting_review():
    """Lane 2: DB update_claim_status called with AWAITING_REVIEW."""
    db = make_db()
    agent = A5NotificationAgent(db=db)
    state = make_state(routing_lane=2)

    await agent.handle(state, [])

    db.update_claim_status.assert_called_once_with(
        "CLM-20260522-TEST", "AWAITING_REVIEW"
    )


@pytest.mark.asyncio
async def test_lane2_pushes_sse_event():
    """Lane 2: SSE event of type 'lane2_result' pushed to session queue."""
    agent = make_agent()
    state = make_state(routing_lane=2, session_id="test-session-lane2")

    await agent.handle(state, [])

    queue = get_or_create_queue("test-session-lane2")
    assert not queue.empty()
    event = await queue.get()
    assert event["type"] == "lane2_result"
    assert "claim_id" in event


@pytest.mark.asyncio
async def test_lane2_no_voucher_generated():
    """Lane 2: voucher_code stays None — no auto-approve."""
    agent = make_agent()
    state = make_state(routing_lane=2)

    result = await agent.handle(state, [])

    assert result.voucher_code is None


@pytest.mark.asyncio
async def test_lane2_sets_result_step():
    """Lane 2: conversation_step advances to 'result'."""
    agent = make_agent()
    state = make_state(routing_lane=2)

    result = await agent.handle(state, [])

    assert result.conversation_step == "result"


# ── Error handling tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a5_db_failure_does_not_crash():
    """A5 continues gracefully if DB update fails."""
    db = make_db()
    db.update_claim_status = AsyncMock(
        side_effect=Exception("Supabase connection timeout")
    )
    agent = A5NotificationAgent(db=db)
    state = make_state(routing_lane=1)

    result = await agent.handle(state, [])

    # Should still generate voucher and push SSE even if DB fails
    assert result.voucher_code is not None
    assert result.notification_sent is True
    assert result.error is None  # A5 handles DB failure gracefully


@pytest.mark.asyncio
async def test_a5_no_db_injected_still_works():
    """A5 works without DB injection — backwards compatible."""
    agent = A5NotificationAgent(db=None)
    state = make_state(routing_lane=1, session_id="test-no-db")

    result = await agent.handle(state, [])

    assert result.voucher_code is not None
    assert result.error is None


@pytest.mark.asyncio
async def test_a5_unknown_lane_does_not_crash():
    """A5 handles unknown routing_lane gracefully — no crash."""
    agent = make_agent()
    state = make_state(routing_lane=None)

    result = await agent.handle(state, [])

    assert result.error is None
