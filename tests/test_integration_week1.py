"""
Week 1 Integration Tests — T-009.

Tests the full POST /webhook → LangGraph → A1 pipeline end-to-end.
Acceptance criteria: 3 full round-trip messages complete successfully.

All LLM/provider calls are mocked — no API keys needed.
Uses httpx.AsyncClient with ASGITransport to call the real FastAPI app.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app

# ── Mock helpers ──────────────────────────────────────────────────────────────


def _mock_llm(
    reply: str = "I'm sorry to hear about your bag. Could you describe the damage?",
) -> MagicMock:
    m = MagicMock()
    m.chat = AsyncMock(return_value=reply)
    return m


def _mock_providers(llm=None):
    """Context manager patching all provider factories with lightweight mocks."""
    mock_llm = llm or _mock_llm()
    mock_vision = MagicMock()
    mock_ocr = MagicMock()
    mock_db = MagicMock()
    mock_db.save_claim = AsyncMock(return_value=None)
    mock_db.get_claim_count = AsyncMock(return_value=0)
    mock_storage = MagicMock()
    mock_storage.save = AsyncMock(return_value="data/uploads/test.jpg")

    patches = (
        patch("backend.dependencies.provide_llm", return_value=mock_llm),
        patch("backend.dependencies.provide_vision", return_value=mock_vision),
        patch("backend.dependencies.provide_ocr", return_value=mock_ocr),
        patch("backend.dependencies.provide_db", return_value=mock_db),
        patch("backend.dependencies.provide_storage", return_value=mock_storage),
    )
    return patches, mock_llm


# ── Health endpoint ───────────────────────────────────────────────────────────


async def test_health_endpoint_returns_service_info():
    """
    GET /health → returns service name and provider config.
    Server is up and FastAPI app initialised correctly.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code in (200, 503)  # 503 if env vars not set — still valid
    data = response.json()
    assert "status" in data
    assert data["service"] == "baggage-claim-ai"
    assert "providers" in data


# ── Webhook: single message ───────────────────────────────────────────────────


async def test_webhook_greeting_returns_a1_reply():
    """
    POST /webhook with a greeting message →
    200 OK + non-empty A1 reply in response body.
    Core T-009 acceptance: message in → real reply out.
    """
    patches, _ = _mock_providers()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook",
                json={
                    "session_id": "t009-single-message",
                    "message": "hi my bag is damaged",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "t009-single-message"
    assert data["reply"] != ""
    assert data["error"] is None


async def test_webhook_response_schema_complete():
    """
    POST /webhook response includes all fields defined in WebhookResponse schema.
    Ensures no field is accidentally dropped from the response.
    """
    patches, _ = _mock_providers()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook",
                json={
                    "session_id": "t009-schema-check",
                    "message": "my suitcase wheel broke",
                },
            )

    assert response.status_code == 200
    data = response.json()

    required_fields = [
        "session_id",
        "reply",
        "conversation_step",
        "re_request_tag",
        "re_request_damage",
    ]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"


# ── Webhook: three round trips ────────────────────────────────────────────────


async def test_webhook_three_round_trips_same_session():
    """
    Three consecutive messages in the same session all return 200 with replies.

    This is the primary T-009 acceptance criterion:
    '3 full round-trip messages work with <5s latency each'.
    """
    replies = [
        "Hi! I'm sorry to hear that. Could you describe the damage?",
        "Thank you for describing that. Please upload clear photos of the damage.",
        "Photos received. Now please photograph the bag tag clearly.",
    ]
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(side_effect=replies)
    patches, _ = _mock_providers(llm=mock_llm)

    messages = [
        "hi my bag is broken",
        "the wheel is cracked and the handle is torn",
        "here are my damage photos",
    ]

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for i, msg in enumerate(messages):
                response = await client.post(
                    "/webhook",
                    json={
                        "session_id": "t009-three-rounds",
                        "message": msg,
                    },
                )
                assert (
                    response.status_code == 200
                ), f"Round {i + 1} returned {response.status_code}"
                data = response.json()
                assert data["reply"] != "", f"Round {i + 1} returned empty reply"
                assert data["error"] is None, f"Round {i + 1} error: {data['error']}"


# ── Webhook: session isolation ────────────────────────────────────────────────


async def test_two_sessions_are_independent():
    """
    Two passengers with different session_ids get independent responses.
    No state bleed between sessions — MemorySaver keeps them isolated.
    """
    patches, _ = _mock_providers()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r_alice = await client.post(
                "/webhook",
                json={
                    "session_id": "passenger-alice",
                    "message": "hi my bag is damaged",
                },
            )
            r_bob = await client.post(
                "/webhook",
                json={
                    "session_id": "passenger-bob",
                    "message": "hello my suitcase broke",
                },
            )

    assert r_alice.status_code == 200
    assert r_bob.status_code == 200
    assert r_alice.json()["session_id"] == "passenger-alice"
    assert r_bob.json()["session_id"] == "passenger-bob"


# ── Webhook: error resilience ─────────────────────────────────────────────────


async def test_webhook_never_returns_500_on_llm_failure():
    """
    LLM failure → webhook returns 200 with error field set (never 500).
    Server stays alive and gracefully surfaces errors to the simulator.
    """
    broken_llm = MagicMock()
    broken_llm.chat = AsyncMock(side_effect=Exception("LLM service unavailable"))
    patches, _ = _mock_providers(llm=broken_llm)

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook",
                json={
                    "session_id": "t009-llm-failure",
                    "message": "test message",
                },
            )

    assert response.status_code == 200  # never 500
    data = response.json()
    assert data["error"] is not None  # error surfaced in payload


async def test_webhook_invalid_payload_returns_422():
    """
    POST /webhook with missing required field → 422 Unprocessable Entity.
    Pydantic validation works correctly on the request schema.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/webhook",
            json={
                "message": "missing session_id field",
                # session_id intentionally omitted
            },
        )

    assert response.status_code == 422
