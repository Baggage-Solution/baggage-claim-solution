"""tests/test_webhook.py — P-007 Webhook Decoupling tests.

Covers:
  - Memory-queue (dev) path: POST /webhook runs pipeline inline, returns WebhookResponse.
  - SQS path: POST /webhook enqueues job, returns {accepted: true, ...} within <500ms.
  - HMAC signature validation (present but wrong → 403; absent → pass-through).
  - _build_job_payload: all WebhookRequest fields serialised correctly.

Authors: Anoushka + Devam (unified branch — P-007)
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.routes.webhook import _build_job_payload
from backend.api.schemas.claim_request import WebhookRequest
from backend.queue_provider.in_memory_queue import InMemoryQueueProvider


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def minimal_webhook_request() -> WebhookRequest:
    """Minimal valid WebhookRequest payload — only required fields."""
    return WebhookRequest(session_id="sess-test-001", message="hello")


@pytest.fixture
def full_webhook_request() -> WebhookRequest:
    """WebhookRequest with all optional echo fields populated."""
    return WebhookRequest(
        session_id="sess-full-002",
        message="my bag is damaged",
        image_paths=["data/uploads/CLM-001/damage_bag.jpg"],
        conversation_history=[{"role": "user", "content": "hello"}],
        conversation_step="damage_photos",
        conversation_ended=False,
        no_damage_detected=False,
        not_a_bag=False,
        non_bag_attempts=0,
        tag_in_damage_photo=False,
        tag_candidate_paths=[],
        processed_damage_paths=[],
        damage_types=["scuff"],
        severity_score=0.6,
        brand_detected="Samsonite",
        is_luxury=False,
        compensation_estimate_usd=45.0,
        processed_tag_paths=[],
        flight_number="AI101",
        pnr="PNR123",
        bag_id="BAG456",
        ocr_confidence=0.92,
        tag_data_complete=True,
        tag_manually_entered=False,
    )


# ──────────────────────────────────────────────────────────────
# _build_job_payload unit tests
# ──────────────────────────────────────────────────────────────

def test_build_job_payload_includes_session_id(minimal_webhook_request):
    """Job payload must contain session_id for the worker to route the reply."""
    job = _build_job_payload(minimal_webhook_request, req_id="req-001")
    assert job["session_id"] == "sess-test-001"


def test_build_job_payload_includes_request_id(minimal_webhook_request):
    """request_id is propagated for CloudWatch trace correlation."""
    job = _build_job_payload(minimal_webhook_request, req_id="req-trace-abc")
    assert job["request_id"] == "req-trace-abc"


def test_build_job_payload_includes_all_echo_fields(full_webhook_request):
    """All echoed A1/A2/A3 state fields must survive the serialisation round-trip."""
    job = _build_job_payload(full_webhook_request, req_id=None)
    assert job["flight_number"] == "AI101"
    assert job["pnr"] == "PNR123"
    assert job["bag_id"] == "BAG456"
    assert job["damage_types"] == ["scuff"]
    assert job["severity_score"] == pytest.approx(0.6)
    assert job["compensation_estimate_usd"] == pytest.approx(45.0)
    assert job["brand_detected"] == "Samsonite"
    assert job["ocr_confidence"] == pytest.approx(0.92)
    assert job["tag_data_complete"] is True


def test_build_job_payload_is_json_serialisable(full_webhook_request):
    """The job dict produced by _build_job_payload must be JSON-serialisable
    so SQS can store it in a MessageBody string."""
    job = _build_job_payload(full_webhook_request, req_id="req-99")
    # This must not raise
    serialised = json.dumps(job)
    assert "session_id" in serialised


def test_build_job_payload_generates_unique_job_ids(minimal_webhook_request):
    """Each call generates a fresh UUID job_id — no collision between claims."""
    job1 = _build_job_payload(minimal_webhook_request, req_id=None)
    job2 = _build_job_payload(minimal_webhook_request, req_id=None)
    assert job1["job_id"] != job2["job_id"]


# ──────────────────────────────────────────────────────────────
# HMAC signature validation
# ──────────────────────────────────────────────────────────────

def test_hmac_validation_skipped_when_secret_not_configured(monkeypatch):
    """When WHATSAPP_APP_SECRET is not set, signature check always passes."""
    from backend.api.routes.webhook import verify_whatsapp_signature

    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    assert verify_whatsapp_signature(b"any body", None) is True
    assert verify_whatsapp_signature(b"any body", "sha256=garbage") is True


def test_hmac_validation_fails_on_wrong_signature(monkeypatch):
    """When WHATSAPP_APP_SECRET is set, a wrong signature returns False."""
    from backend.api.routes.webhook import verify_whatsapp_signature

    monkeypatch.setenv("WHATSAPP_APP_SECRET", "supersecret")
    assert verify_whatsapp_signature(b"body", "sha256=wronghex") is False


def test_hmac_validation_passes_on_correct_signature(monkeypatch):
    """When WHATSAPP_APP_SECRET is set, the correct HMAC passes."""
    import hashlib
    import hmac as _hmac

    from backend.api.routes.webhook import verify_whatsapp_signature

    secret = "supersecret"
    body = b"test body"
    monkeypatch.setenv("WHATSAPP_APP_SECRET", secret)
    correct_sig = "sha256=" + _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_whatsapp_signature(body, correct_sig) is True


# ──────────────────────────────────────────────────────────────
# SQS path — enqueue-and-return (QUEUE_PROVIDER=sqs)
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sqs_path_returns_accepted_true_immediately():
    """When a non-InMemory queue provider is active, POST /webhook must return
    {accepted: true, session_id, job_id} without running the pipeline."""
    # Use a mock queue that is NOT an InMemoryQueueProvider
    mock_queue = AsyncMock()
    mock_queue.enqueue = AsyncMock(return_value="sqs-message-id-001")
    # Crucially: mock_queue is not an InMemoryQueueProvider instance

    with patch("backend.api.routes.webhook.provide_queue", return_value=mock_queue):
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        response = client.post(
            "/webhook",
            json={"session_id": "sess-sqs-001", "message": "hello"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["session_id"] == "sess-sqs-001"
    assert "job_id" in body
    mock_queue.enqueue.assert_called_once()


@pytest.mark.asyncio
async def test_sqs_path_enqueue_failure_returns_503():
    """If enqueue() raises, the webhook must return 503 — not silently succeed."""
    from botocore.exceptions import ClientError

    mock_queue = AsyncMock()
    mock_queue.enqueue = AsyncMock(
        side_effect=ClientError({"Error": {"Code": "500", "Message": "fail"}}, "SendMessage")
    )

    with patch("backend.api.routes.webhook.provide_queue", return_value=mock_queue):
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        response = client.post(
            "/webhook",
            json={"session_id": "sess-sqs-fail", "message": "hello"},
        )

    assert response.status_code == 503


# ──────────────────────────────────────────────────────────────
# Memory / dev path — backward compat
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_path_runs_pipeline_inline():
    """When QUEUE_PROVIDER=memory (InMemoryQueueProvider), the pipeline runs
    inline and returns a full WebhookResponse — simulator stays functional."""
    from backend.graph.state import ClaimState

    memory_queue = InMemoryQueueProvider()

    mock_state = ClaimState(
        session_id="sess-mem-001",
        a1_response="Hello, how can I help?",
        conversation_step="greeting",
    )

    with (
        patch("backend.api.routes.webhook.provide_queue", return_value=memory_queue),
        patch(
            "backend.api.routes.webhook.orchestrator.run",
            AsyncMock(return_value=mock_state),
        ),
    ):
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        response = client.post(
            "/webhook",
            json={"session_id": "sess-mem-001", "message": "hi"},
        )

    assert response.status_code == 200
    body = response.json()
    # Dev path returns the full WebhookResponse — not {accepted: true}
    assert "reply" in body
    assert body["session_id"] == "sess-mem-001"
    # The job was NOT enqueued (dequeue returns nothing)
    remaining = await memory_queue.dequeue()
    assert remaining == []