from __future__ import annotations

import logging
from fastapi import APIRouter, Request, UploadFile, File, Form
from typing import List, Optional

from backend.api.schemas.claim_request import WebhookRequest
from backend.api.schemas.claim_response import WebhookResponse
from backend.core.exceptions import AppError
from backend.graph.orchestrator import ClaimOrchestrator
from backend.dependencies import provide_storage

router = APIRouter(tags=["Webhook"])
logger = logging.getLogger(__name__)
orchestrator = ClaimOrchestrator()


@router.post("/webhook", response_model=WebhookResponse)
async def webhook(request: Request, payload: WebhookRequest) -> WebhookResponse:
    """
    Main entry point for all incoming messages from the WhatsApp simulator.
    Receives text message + optional pre-uploaded image paths, runs the 5-agent pipeline.
    (T-004 + T-009)
    """
    req_id = getattr(request.state, "request_id", None)

    try:
        state = await orchestrator.run(
            session_id=payload.session_id,
            passenger_message=payload.message,
            image_paths=payload.image_paths or [],
            conversation_history=payload.conversation_history or [],
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
            error=state.error,
        )

    except AppError as exc:
        logger.warning("webhook_app_error", extra={"error": exc.message, "code": exc.code})
        return WebhookResponse(session_id=payload.session_id, reply="", error=exc.message)

    except Exception as exc:
        logger.exception("webhook_unexpected_error")
        return WebhookResponse(session_id=payload.session_id, reply="", error=str(exc))


@router.post("/upload")
async def upload_image(
    session_id: str = Form(...),
    claim_id: str = Form(...),
    photo_type: str = Form(...),  # "damage" or "tag"
    file: UploadFile = File(...),
):
    """
    Upload a damage or tag photo. Returns the stored file path for use in /webhook payload.
    (T-013)
    """
    storage = provide_storage()
    file_bytes = await file.read()
    filename = f"{photo_type}_{file.filename}"
    path = await storage.save(file_bytes, filename, claim_id)
    return {"path": path, "filename": filename}
