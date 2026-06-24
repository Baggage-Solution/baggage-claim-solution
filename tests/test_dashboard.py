"""
Tests for agent dashboard backend endpoints — T-017.
Covers GET /claims/pending and POST /decision.
All DB calls mocked — no real Supabase connection needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


def make_mock_db(claims=None, existing_claim=None):
    """
    Mock DBProvider for the dashboard endpoints.
    /decision calls get_claim() then update_claim() — both must be AsyncMock.
    update_claim() echoes the fields back merged onto the existing row.
    """
    db = MagicMock()
    db.get_claims_by_status = AsyncMock(return_value=claims or [])
    db.update_claim_status = AsyncMock(return_value=None)

    base = existing_claim or {
        "id": "CLM-20260522-001",
        "status": "AWAITING_REVIEW",
        "compensation": 150.0,
        "voucher_code": None,
        "routing_lane": 2,
    }
    db.get_claim = AsyncMock(return_value=dict(base))

    async def _update(claim_id, fields):
        merged = dict(base)
        merged.update(fields)
        merged["id"] = claim_id
        return merged

    db.update_claim = AsyncMock(side_effect=_update)
    return db


# ── GET /claims/pending ───────────────────────────────────────────────────────


async def test_get_pending_claims_returns_empty_when_none():
    """GET /claims/pending → empty list when no AWAITING_REVIEW claims."""
    with patch(
        "backend.api.routes.decision.provide_db", return_value=make_mock_db(claims=[])
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/claims/pending")

    assert response.status_code == 200
    data = response.json()
    assert data["claims"] == []
    assert data["count"] == 0


async def test_get_pending_claims_returns_awaiting_review_list():
    """GET /claims/pending → returns correct claims and count."""
    mock_claims = [
        {"id": "CLM-001", "status": "AWAITING_REVIEW", "compensation": 150.0},
        {"id": "CLM-002", "status": "AWAITING_REVIEW", "compensation": 75.0},
    ]
    with patch(
        "backend.api.routes.decision.provide_db",
        return_value=make_mock_db(claims=mock_claims),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/claims/pending")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["claims"]) == 2


async def test_get_pending_calls_db_with_awaiting_review_status():
    """DB must be queried with 'AWAITING_REVIEW' — not any other status."""
    mock_db = make_mock_db()
    with patch("backend.api.routes.decision.provide_db", return_value=mock_db):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/claims/pending")

    mock_db.get_claims_by_status.assert_called_once_with("AWAITING_REVIEW")


# ── POST /decision ────────────────────────────────────────────────────────────


async def test_approve_updates_status_to_resolved():
    """POST /decision approve → DB updated RESOLVED, response confirms."""
    mock_db = make_mock_db()
    with patch("backend.api.routes.decision.provide_db", return_value=mock_db):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/decision",
                json={
                    "claim_id": "CLM-20260522-001",
                    "action": "approve",
                    "agent_id": "AGENT-001",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "RESOLVED"
    assert data["claim_id"] == "CLM-20260522-001"
    mock_db.update_claim.assert_called_once()
    _, fields = mock_db.update_claim.call_args[0]
    assert fields["status"] == "RESOLVED"
    assert fields.get("voucher_code")
    assert data["voucher_code"]


async def test_reject_updates_status_to_rejected():
    """POST /decision reject → DB updated REJECTED, response confirms."""
    mock_db = make_mock_db()
    with patch("backend.api.routes.decision.provide_db", return_value=mock_db):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/decision",
                json={
                    "claim_id": "CLM-20260522-002",
                    "action": "reject",
                    "agent_id": "AGENT-001",
                    "notes": "Photos look suspicious",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "REJECTED"
    mock_db.update_claim.assert_called_once()
    _, fields = mock_db.update_claim.call_args[0]
    assert fields["status"] == "REJECTED"


async def test_invalid_action_returns_error_without_db_call():
    """POST /decision with invalid action → error, DB update never called."""
    mock_db = make_mock_db()
    with patch("backend.api.routes.decision.provide_db", return_value=mock_db):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/decision",
                json={
                    "claim_id": "CLM-001",
                    "action": "transfer",
                    "agent_id": "AGENT-001",
                },
            )

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    mock_db.update_claim.assert_not_called()


async def test_decision_response_includes_agent_id():
    """Audit trail: response message contains agent_id."""
    with patch("backend.api.routes.decision.provide_db", return_value=make_mock_db()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/decision",
                json={
                    "claim_id": "CLM-001",
                    "action": "approve",
                    "agent_id": "AGENT-SMITH",
                },
            )

    assert "AGENT-SMITH" in response.json()["message"]


async def test_decision_missing_required_field_returns_422():
    """POST /decision without claim_id → 422 Pydantic validation error."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/decision",
            json={
                "action": "approve",
                "agent_id": "AGENT-001",
            },
        )

    assert response.status_code == 422
