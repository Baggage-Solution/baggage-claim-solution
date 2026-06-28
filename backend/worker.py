"""backend/worker.py — ECS Worker Entrypoint (P-008).

Long-poll loop: dequeue from QueueProvider → rebuild ClaimState →
run LangGraph pipeline → send reply via ChannelProvider → ack message.

The same Docker image runs as API server (uvicorn backend.main:app) or as
this worker (python -m backend.worker). The ECS task definition's `command`
field selects which entrypoint starts.

Graceful shutdown:
    SIGTERM from ECS drain triggers a shutdown flag. The loop finishes any
    in-flight job, then exits cleanly — ECS waits up to `deregistration_delay`
    (default 60s) before force-killing the task.

Authors: Aditya + Devam (unified branch — P-008)
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

# ── asyncio Windows fix — must run before any event loop creation ─────────────
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ─────────────────────────────────────────────────────────────────────────────

from backend.config import get_settings
from backend.core.logging import configure_logging
from backend.dependencies import provide_channel, provide_queue
from backend.graph.orchestrator import ClaimOrchestrator
from backend.graph.state import ClaimState

settings = get_settings()
configure_logging(level=settings.log_level, fmt=settings.log_format)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
_DEQUEUE_BATCH_SIZE = 5          # SQS max per call is 10; 5 keeps latency tight
_SHUTDOWN_TIMEOUT_SECONDS = 60   # Max time to finish in-flight before hard exit


# ── Orchestrator singleton — one per worker process ───────────────────────────
_orchestrator = ClaimOrchestrator()

# ── Shutdown flag — set by SIGTERM handler ─────────────────────────────────────
_shutdown_requested = False


def _handle_sigterm(signum: int, frame: Any) -> None:  # noqa: ANN401
    """Set the shutdown flag when ECS sends SIGTERM.

    The long-poll loop checks this flag at the top of each iteration.
    Any job already dequeued will finish before the process exits.
    """
    global _shutdown_requested
    logger.info("worker_sigterm_received — draining in-flight jobs before exit")
    _shutdown_requested = True


def _rebuild_state_from_job(job: dict[str, Any]) -> ClaimState:
    """Reconstruct a ClaimState dataclass from the flat job dict.

    The job dict was produced by webhook.py::_build_job_payload().
    Every field present there has a matching kwarg here. Unknown keys
    are ignored (.pop with default) so future fields added to the job
    payload don't crash older worker deployments during a rolling update.

    Args:
        job: Dict dequeued from SQS (or InMemoryQueueProvider in tests).

    Returns:
        ClaimState ready to be passed to ClaimOrchestrator.run().
    """
    return ClaimState(
        # Identity
        session_id=job.get("session_id", ""),
        request_id=job.get("request_id"),
        # Passenger turn
        passenger_message=job.get("message", ""),
        image_paths=job.get("image_paths", []),
        conversation_history=job.get("conversation_history", []),
        conversation_step=job.get("conversation_step", "greeting"),
        # A1 echoed state
        conversation_ended=job.get("conversation_ended", False),
        # A2 echoed state
        no_damage_detected=job.get("no_damage_detected", False),
        not_a_bag=job.get("not_a_bag", False),
        last_object_description=job.get("last_object_description"),
        non_bag_attempts=job.get("non_bag_attempts", 0),
        tag_in_damage_photo=job.get("tag_in_damage_photo", False),
        tag_candidate_paths=job.get("tag_candidate_paths", []),
        processed_damage_paths=job.get("processed_damage_paths", []),
        damage_types=job.get("damage_types", []),
        severity_score=job.get("severity_score", 0.0),
        brand_detected=job.get("brand_detected"),
        is_luxury=job.get("is_luxury", False),
        compensation_estimate_usd=job.get("compensation_estimate_usd", 0.0),
        # A3 echoed state
        processed_tag_paths=job.get("processed_tag_paths", []),
        flight_number=job.get("flight_number"),
        pnr=job.get("pnr"),
        bag_id=job.get("bag_id"),
        ocr_confidence=job.get("ocr_confidence", 0.0),
        tag_data_complete=job.get("tag_data_complete", False),
        tag_manually_entered=job.get("tag_manually_entered", False),
        manual_tag_text=job.get("manual_tag_text"),
        manual_flight_number=job.get("manual_flight_number"),
        manual_pnr=job.get("manual_pnr"),
        manual_bag_id=job.get("manual_bag_id"),
        offer_manual_entry=job.get("offer_manual_entry", False),
    )


async def process_job(job: dict[str, Any], queue: Any, channel: Any) -> None:
    """Process one dequeued job end-to-end.

    Steps:
        1. Rebuild ClaimState from the flat job dict.
        2. Run the full LangGraph pipeline (A1 → A2 → A3 → A4 → A5).
        3. A5 already pushes the result via ChannelProvider inside the pipeline.
        4. Ack the message to delete it from SQS.
        5. On any error: log and DO NOT ack — SQS visibility timeout will
           expire and the job will be redelivered (up to redrive limit → DLQ).

    Args:
        job: Flat dict including `_receipt_handle` from QueueProvider.dequeue().
        queue: The active QueueProvider (SQS or in-memory).
        channel: The active ChannelProvider (whatsapp or webhook/SSE).
    """
    receipt_handle: str = job.get("_receipt_handle", "")
    session_id: str = job.get("session_id", "unknown")
    job_id: str = job.get("job_id", "unknown")

    logger.info(
        "worker_job_started",
        extra={
            "session_id": session_id,
            "job_id": job_id,
            "request_id": job.get("request_id"),
        },
    )

    try:
        state = _rebuild_state_from_job(job)

        # Run the full 5-agent pipeline.
        # A5 internally calls channel.send_message() — in production that
        # goes to WhatsAppChannelProvider (P-024); in dev/tests it pushes
        # to the SSE queue via WebhookChannelProvider.
        state = await _orchestrator.run(
            session_id=state.session_id,
            passenger_message=state.passenger_message,
            image_paths=state.image_paths,
            conversation_history=state.conversation_history,
            conversation_step=state.conversation_step,
            conversation_ended=state.conversation_ended,
            no_damage_detected=state.no_damage_detected,
            not_a_bag=state.not_a_bag,
            last_object_description=state.last_object_description,
            non_bag_attempts=state.non_bag_attempts,
            tag_in_damage_photo=state.tag_in_damage_photo,
            tag_candidate_paths=state.tag_candidate_paths,
            processed_damage_paths=state.processed_damage_paths,
            damage_types=state.damage_types,
            severity_score=state.severity_score,
            brand_detected=state.brand_detected,
            is_luxury=state.is_luxury,
            compensation_estimate_usd=state.compensation_estimate_usd,
            processed_tag_paths=state.processed_tag_paths,
            flight_number=state.flight_number,
            pnr=state.pnr,
            bag_id=state.bag_id,
            ocr_confidence=state.ocr_confidence,
            tag_data_complete=state.tag_data_complete,
            tag_manually_entered=state.tag_manually_entered,
            manual_tag_text=state.manual_tag_text,
            manual_flight_number=state.manual_flight_number,
            manual_pnr=state.manual_pnr,
            manual_bag_id=state.manual_bag_id,
            offer_manual_entry=state.offer_manual_entry,
            request_id=state.request_id,
        )

        if state.error:
            logger.warning(
                "worker_job_pipeline_error",
                extra={"session_id": session_id, "error": state.error},
            )
            # Still ack — the error was caught inside the pipeline and the
            # reply was already sent by A5's error handler. Re-driving the
            # message would duplicate the reply.

        # Ack: delete the message from SQS. Must only happen after the
        # pipeline returns so we never lose a job mid-processing.
        await queue.ack(receipt_handle)

        logger.info(
            "worker_job_completed",
            extra={
                "session_id": session_id,
                "job_id": job_id,
                "routing_lane": state.routing_lane,
                "claim_id": state.claim_id,
            },
        )

    except Exception as exc:
        # Do NOT ack — let SQS redeliver (up to max receive count → DLQ).
        logger.exception(
            "worker_job_failed — not acking, will be redelivered",
            extra={
                "session_id": session_id,
                "job_id": job_id,
                "error": str(exc),
            },
        )


async def main() -> None:
    """Long-poll dequeue loop — runs until SIGTERM.

    On each iteration:
        1. Check shutdown flag — exit if set.
        2. Dequeue up to _DEQUEUE_BATCH_SIZE jobs.
        3. Process each job concurrently with asyncio.gather.
        4. Immediately loop (no sleep — SQS long-poll already waits 20s
           on empty queues via WaitTimeSeconds=20 inside dequeue()).
    """
    logger.info("worker_started", extra={"batch_size": _DEQUEUE_BATCH_SIZE})

    # Resolve providers once at startup — same process lifecycle as the API.
    queue = provide_queue()
    channel = provide_channel()

    while not _shutdown_requested:
        try:
            jobs = await queue.dequeue(max_messages=_DEQUEUE_BATCH_SIZE)
        except Exception as exc:
            # Network / credential error — log and retry after a brief pause
            # to avoid hammering SQS on a transient outage.
            logger.exception(
                "worker_dequeue_error — retrying in 5s", extra={"error": str(exc)}
            )
            await asyncio.sleep(5)
            continue

        if not jobs:
            # Empty receive (SQS long-poll already waited 20s). Loop again.
            continue

        logger.info("worker_dequeue_batch", extra={"count": len(jobs)})

        # Process all jobs in the batch concurrently.
        # Each process_job() call handles its own error — gather() won't
        # cancel sibling tasks on a single failure.
        await asyncio.gather(
            *[process_job(job, queue, channel) for job in jobs],
            return_exceptions=False,
        )

    logger.info("worker_shutdown_complete")


if __name__ == "__main__":
    # Register SIGTERM handler before starting the event loop so the handler
    # is in place even if the process receives SIGTERM during startup.
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)   # Ctrl-C in dev
    asyncio.run(main())