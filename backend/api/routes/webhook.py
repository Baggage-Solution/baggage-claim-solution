from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from typing import List, Optional

from fastapi import (APIRouter, File, Form, Header, HTTPException, Request,
                     UploadFile)
from fastapi.responses import StreamingResponse

from backend.api.schemas.claim_request import WebhookRequest
from backend.api.schemas.claim_response import WebhookResponse
from backend.core.exceptions import AppError
from backend.dependencies import provide_storage
from backend.graph.orchestrator import ClaimOrchestrator

router = APIRouter(tags=["Webhook"])
logger = logging.getLogger(__name__)
orchestrator = ClaimOrchestrator()


def verify_whatsapp_signature(payload: bytes, signature_header: Optional[str]) -> bool:
    app_secret = os.getenv("WHATSAPP_APP_SECRET")
    if not app_secret:
        logger.debug(
            "signature_verification_skipped — WHATSAPP_APP_SECRET not configured"
        )
        return True
    if not signature_header:
        logger.warning(
            "signature_verification_failed — missing X-Hub-Signature-256 header"
        )
        return False
    expected = (
        "sha256="
        + hmac.new(app_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    )
    is_valid = hmac.compare_digest(expected, signature_header)
    if not is_valid:
        logger.warning("signature_verification_failed — signature mismatch")
    return is_valid


@router.post("/webhook", response_model=WebhookResponse)
async def webhook(
    request: Request,
    payload: WebhookRequest,
    x_hub_signature_256: Optional[str] = Header(default=None),
) -> WebhookResponse:
    body_bytes = await request.body()
    if not verify_whatsapp_signature(body_bytes, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid X-Hub-Signature-256")

    req_id = getattr(request.state, "request_id", None)

    logger.info(
        "webhook_received",
        extra={
            "session_id": payload.session_id,
            "message_preview": payload.message[:50],
            "image_count": len(payload.image_paths or []),
            "request_id": req_id,
        },
    )

    try:
        state = await orchestrator.run(
            session_id=payload.session_id,
            passenger_message=payload.message,
            image_paths=payload.image_paths or [],
            conversation_history=payload.conversation_history or [],
            conversation_step=payload.conversation_step or "greeting",
            # A2 echoed results
            conversation_ended=payload.conversation_ended or False,
            no_damage_detected=payload.no_damage_detected or False,
            # Issue #1 — object gate
            not_a_bag=payload.not_a_bag or False,
            last_object_description=payload.last_object_description,
            non_bag_attempts=payload.non_bag_attempts or 0,
            # Issue #2/#4 — tag in damage photo
            tag_in_damage_photo=payload.tag_in_damage_photo or False,
            tag_candidate_paths=payload.tag_candidate_paths or [],
            processed_damage_paths=payload.processed_damage_paths or [],
            damage_types=payload.damage_types or [],
            severity_score=payload.severity_score or 0.0,
            brand_detected=payload.brand_detected,
            is_luxury=payload.is_luxury or False,
            compensation_estimate_usd=payload.compensation_estimate_usd or 0.0,
            # A3 echoed results
            processed_tag_paths=payload.processed_tag_paths or [],
            flight_number=payload.flight_number,
            pnr=payload.pnr,
            bag_id=payload.bag_id,
            ocr_confidence=payload.ocr_confidence or 0.0,
            tag_data_complete=payload.tag_data_complete or False,
            tag_manually_entered=payload.tag_manually_entered or False,
            # Issue #3 — manual tag entry
            manual_tag_text=payload.manual_tag_text,
            manual_flight_number=payload.manual_flight_number,
            manual_pnr=payload.manual_pnr,
            manual_bag_id=payload.manual_bag_id,
            offer_manual_entry=payload.offer_manual_entry or False,
            request_id=req_id,
        )

        return WebhookResponse(
            session_id=payload.session_id,
            reply=state.a1_response or "",
            claim_id=state.claim_id,
            routing_lane=state.routing_lane,
            voucher_code=state.voucher_code,
            conversation_step=state.conversation_step,
            re_request_tag=state.re_request_tag,
            re_request_damage=state.re_request_damage,
            conversation_ended=state.conversation_ended,
            no_damage_detected=state.no_damage_detected,
            # Issue #1 — object gate
            not_a_bag=state.not_a_bag,
            last_object_description=state.last_object_description,
            non_bag_attempts=state.non_bag_attempts,
            # Issue #2/#4 — tag in damage photo
            tag_in_damage_photo=state.tag_in_damage_photo,
            tag_candidate_paths=state.tag_candidate_paths,
            # Echo A2 results back
            processed_damage_paths=state.processed_damage_paths,
            damage_types=state.damage_types,
            severity_score=state.severity_score,
            brand_detected=state.brand_detected,
            is_luxury=state.is_luxury,
            compensation_estimate_usd=state.compensation_estimate_usd,
            # Echo A3 results back
            processed_tag_paths=state.processed_tag_paths,
            flight_number=state.flight_number,
            pnr=state.pnr,
            bag_id=state.bag_id,
            ocr_confidence=state.ocr_confidence,
            tag_data_complete=state.tag_data_complete,
            tag_manually_entered=state.tag_manually_entered,
            # Issue #3 — manual tag entry
            offer_manual_entry=state.offer_manual_entry,
            error=state.error,
        )

    except AppError as exc:
        logger.warning(
            "webhook_app_error", extra={"error": exc.message, "code": exc.code}
        )
        return WebhookResponse(
            session_id=payload.session_id, reply="", error=exc.message
        )

    except Exception as exc:
        logger.exception("webhook_unexpected_error")
        return WebhookResponse(session_id=payload.session_id, reply="", error=str(exc))


@router.post("/upload")
async def upload_image(
    session_id: str = Form(...),
    claim_id: str = Form(...),
    photo_type: str = Form(...),  # "damage" or "tag"
    file: UploadFile = File(...),
) -> dict:
    """
    Upload a damage or bag tag photo for a claim.

    The backend prefixes photo_type onto the saved filename:
        filename = f"{photo_type}_{file.filename}"
    Tag uploads always become "tag_<name>", damage uploads "damage_<name>".
    All downstream agents rely on this prefix to classify images — it is
    reliable because the backend controls the naming, not the user.
    """
    storage = provide_storage()
    file_bytes = await file.read()
    filename = f"{photo_type}_{file.filename}"
    path = await storage.save(file_bytes, filename, claim_id)

    logger.info(
        "upload_saved",
        extra={
            "session_id": session_id,
            "claim_id": claim_id,
            "photo_type": photo_type,
            "upload_filename": filename,
        },
    )

    return {"path": path, "filename": filename}


@router.get("/events/{session_id}")
async def sse_events(session_id: str):
    from backend.agents.a5_notification import get_or_create_queue

    queue = get_or_create_queue(session_id)

    async def event_generator():
        yield f"data: {json.dumps({'type': 'connected', 'session_id': session_id})}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            except asyncio.CancelledError:
                logger.info("sse_client_disconnected", extra={"session_id": session_id})
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )