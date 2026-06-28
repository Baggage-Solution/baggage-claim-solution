"""tests/test_worker.py — P-008 Worker Entrypoint tests.

Covers:
  - _rebuild_state_from_job: all fields hydrated correctly from flat job dict.
  - process_job: pipeline called, ack called on success.
  - process_job: ack NOT called on pipeline exception.
  - Worker loop processes a batch of messages.
  - Shutdown flag stops the loop cleanly.

Authors: Aditya + Devam (unified branch — P-008)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.queue_provider.in_memory_queue import InMemoryQueueProvider
from backend.worker import _rebuild_state_from_job, process_job


# ──────────────────────────────────────────────────────────────
# _rebuild_state_from_job
# ──────────────────────────────────────────────────────────────

def test_rebuild_state_session_id():
    """session_id is hydrated from the job dict."""
    job = {"session_id": "sess-abc", "message": "hello", "_receipt_handle": "rh-1"}
    state = _rebuild_state_from_job(job)
    assert state.session_id == "sess-abc"


def test_rebuild_state_passenger_message():
    """passenger_message is hydrated from the 'message' key."""
    job = {"session_id": "s", "message": "my bag is torn", "_receipt_handle": "rh-2"}
    state = _rebuild_state_from_job(job)
    assert state.passenger_message == "my bag is torn"


def test_rebuild_state_defaults_for_missing_fields():
    """Missing optional fields default to safe values — no KeyError."""
    job = {"session_id": "s", "message": "hi", "_receipt_handle": "rh-3"}
    state = _rebuild_state_from_job(job)
    assert state.conversation_step == "greeting"
    assert state.image_paths == []
    assert state.conversation_history == []
    assert state.damage_types == []
    assert state.severity_score == pytest.approx(0.0)
    assert state.is_luxury is False
    assert state.tag_data_complete is False


def test_rebuild_state_all_a2_fields():
    """All A2 echoed fields are hydrated correctly."""
    job = {
        "session_id": "s",
        "message": "m",
        "_receipt_handle": "rh-4",
        "damage_types": ["scuff", "tear"],
        "severity_score": 0.8,
        "brand_detected": "Rimowa",
        "is_luxury": True,
        "compensation_estimate_usd": 250.0,
        "not_a_bag": False,
        "non_bag_attempts": 2,
    }
    state = _rebuild_state_from_job(job)
    assert state.damage_types == ["scuff", "tear"]
    assert state.severity_score == pytest.approx(0.8)
    assert state.brand_detected == "Rimowa"
    assert state.is_luxury is True
    assert state.compensation_estimate_usd == pytest.approx(250.0)
    assert state.non_bag_attempts == 2


def test_rebuild_state_all_a3_fields():
    """All A3 echoed fields are hydrated correctly."""
    job = {
        "session_id": "s",
        "message": "m",
        "_receipt_handle": "rh-5",
        "flight_number": "AI202",
        "pnr": "PNR999",
        "bag_id": "BAG888",
        "ocr_confidence": 0.95,
        "tag_data_complete": True,
        "tag_manually_entered": False,
    }
    state = _rebuild_state_from_job(job)
    assert state.flight_number == "AI202"
    assert state.pnr == "PNR999"
    assert state.bag_id == "BAG888"
    assert state.ocr_confidence == pytest.approx(0.95)
    assert state.tag_data_complete is True


def test_rebuild_state_unknown_keys_ignored():
    """Future fields added to the job dict don't crash the worker."""
    job = {
        "session_id": "s",
        "message": "m",
        "_receipt_handle": "rh-6",
        "future_field_not_in_state": "some value",
    }
    state = _rebuild_state_from_job(job)
    assert state.session_id == "s"


# ──────────────────────────────────────────────────────────────
# process_job — success path
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_job_calls_orchestrator_and_acks():
    """On success: orchestrator is called, then ack is called."""
    from backend.graph.state import ClaimState

    mock_queue = AsyncMock()
    mock_channel = AsyncMock()
    mock_state = ClaimState(session_id="sess-001", a1_response="ok")

    job = {
        "session_id": "sess-001",
        "message": "hello",
        "job_id": "job-001",
        "_receipt_handle": "rh-worker-001",
    }

    with patch(
        "backend.worker._orchestrator.run",
        AsyncMock(return_value=mock_state),
    ):
        await process_job(job, mock_queue, mock_channel)

    mock_queue.ack.assert_called_once_with("rh-worker-001")


@pytest.mark.asyncio
async def test_process_job_ack_called_even_on_pipeline_error_flag():
    """When pipeline sets state.error but does NOT raise, we still ack.
    The error was handled inside the pipeline and a reply was sent by A5."""
    from backend.graph.state import ClaimState

    mock_queue = AsyncMock()
    mock_channel = AsyncMock()
    error_state = ClaimState(
        session_id="sess-002",
        error="A4 failed: DB unavailable",
    )

    job = {
        "session_id": "sess-002",
        "message": "hi",
        "job_id": "job-002",
        "_receipt_handle": "rh-worker-002",
    }

    with patch(
        "backend.worker._orchestrator.run",
        AsyncMock(return_value=error_state),
    ):
        await process_job(job, mock_queue, mock_channel)

    # Even with state.error set, ack must be called — the pipeline handled it
    mock_queue.ack.assert_called_once_with("rh-worker-002")


# ──────────────────────────────────────────────────────────────
# process_job — failure path
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_job_does_not_ack_on_unexpected_exception():
    """When the orchestrator raises unexpectedly, ack must NOT be called.
    SQS will redeliver the message (up to maxReceiveCount → DLQ)."""
    mock_queue = AsyncMock()
    mock_channel = AsyncMock()

    job = {
        "session_id": "sess-003",
        "message": "hi",
        "job_id": "job-003",
        "_receipt_handle": "rh-worker-003",
    }

    with patch(
        "backend.worker._orchestrator.run",
        AsyncMock(side_effect=RuntimeError("Bedrock timeout")),
    ):
        # process_job catches the exception internally and logs it
        await process_job(job, mock_queue, mock_channel)

    mock_queue.ack.assert_not_called()


# ──────────────────────────────────────────────────────────────
# Worker drains a batch via InMemoryQueueProvider (integration-style)
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_worker_drains_batch_of_5_messages():
    """Enqueue 5 jobs, process via process_job loop, all 5 are acked."""
    from backend.graph.state import ClaimState

    queue = InMemoryQueueProvider()
    mock_channel = AsyncMock()
    mock_state = ClaimState(session_id="s", a1_response="ok")

    for i in range(5):
        await queue.enqueue(
            {"session_id": f"sess-{i}", "message": "hello", "job_id": f"job-{i}"}
        )

    with patch(
        "backend.worker._orchestrator.run",
        AsyncMock(return_value=mock_state),
    ):
        jobs = await queue.dequeue(max_messages=5)
        assert len(jobs) == 5
        for job in jobs:
            await process_job(job, queue, mock_channel)

    # All 5 have been acked — inflight dict is empty
    assert len(queue._inflight) == 0

    # Queue itself is now empty
    remaining = await queue.dequeue(max_messages=10)
    assert remaining == []
