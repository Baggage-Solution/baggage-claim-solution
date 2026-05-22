from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import List, Optional

from fastapi import (APIRouter, File, Form, Header, HTTPException, Request,
                     UploadFile)

from backend.api.schemas.claim_request import WebhookRequest
from backend.api.schemas.claim_response import WebhookResponse
from backend.core.exceptions import AppError
from backend.dependencies import provide_storage
from backend.graph.orchestrator import ClaimOrchestrator

router = APIRouter(tags=["Webhook"])
logger = logging.getLogger(__name__)
orchestrator = ClaimOrchestrator()


def verify_whatsapp_signature(payload: bytes, signature_header: Optional[str]) -> bool:
    """
    Verify the X-Hub-Signature-256 header sent by WhatsApp Cloud API.

    In POC mode (no WHATSAPP_APP_SECRET set), verification is skipped
    so the simulator can call /webhook freely without signing requests.

    Args:
        payload: Raw request body bytes.
        signature_header: Value of the X-Hub-Signature-256 header.

    Returns:
        True if signature is valid or if POC mode (secret not configured).
        False if secret is set but signature is missing or does not match.
    """
    app_secret = os.getenv("WHATSAPP_APP_SECRET")

    # POC mode — secret not set, skip verification
    if not app_secret:
        logger.debug(
            "signature_verification_skipped — WHATSAPP_APP_SECRET not configured"
        )
        return True

    # Secret is set but header is missing
    if not signature_header:
        logger.warning(
            "signature_verification_failed — missing X-Hub-Signature-256 header"
        )
        return False

    # Compute expected signature
    expected = (
        "sha256="
        + hmac.new(
            app_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
    )

    # Constant-time compare to prevent timing attacks
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
    """
    Main entry point for all incoming messages from the WhatsApp simulator.

    Verifies request signature (stub for POC — skipped when secret not set),
    then runs the full 5-agent LangGraph pipeline and returns the response.

    Args:
        request: Raw FastAPI request object (for body bytes + request_id).
        payload: Parsed WebhookRequest with session_id, message, image_paths.
        x_hub_signature_256: Optional WhatsApp signature header for verification.

    Returns:
        WebhookResponse with A1 reply, claim_id, routing_lane, voucher_code etc.

    Raises:
        HTTPException 403: If signature verification fails (only when secret is set).
    """
    # ── Signature verification ──────────────────────────────────────────────
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

    Saves the file to local storage and returns the path
    to include in the next /webhook request payload.

    Args:
        session_id: Passenger session identifier.
        claim_id: Claim this photo belongs to.
        photo_type: Either "damage" or "tag".
        file: The uploaded image file.

    Returns:
        dict with path and filename of the saved file.
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
