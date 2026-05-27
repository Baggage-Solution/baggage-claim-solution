from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.dependencies import provide_db

router = APIRouter(tags=["Agent Dashboard"])
logger = logging.getLogger(__name__)


class DecisionRequest(BaseModel):
    claim_id: str
    action: str  # "approve" | "reject"
    agent_id: str
    notes: Optional[str] = None
    modified_compensation: Optional[float] = None


class DecisionResponse(BaseModel):
    claim_id: str
    status: str
    message: str


@router.post("/decision", response_model=DecisionResponse)
async def agent_decision(payload: DecisionRequest) -> DecisionResponse:
    """
    Called by the Lane 2 agent dashboard when staff approves or rejects a claim.

    Actions:
    - approve → updates DB status to RESOLVED
    - reject  → updates DB status to REJECTED

    Both actions are logged with agent_id for audit trail.
    No auth for POC — add JWT middleware in Phase 2.
    """
    if payload.action not in ("approve", "reject"):
        return DecisionResponse(
            claim_id=payload.claim_id,
            status="error",
            message=f"Invalid action '{payload.action}'. Must be 'approve' or 'reject'.",
        )

    db = provide_db()
    new_status = "RESOLVED" if payload.action == "approve" else "REJECTED"

    await db.update_claim_status(payload.claim_id, new_status)

    logger.info(
        "agent_decision_completed",
        extra={
            "claim_id": payload.claim_id,
            "action": payload.action,
            "new_status": new_status,
            "agent_id": payload.agent_id,
            "notes": payload.notes,
        },
    )

    return DecisionResponse(
        claim_id=payload.claim_id,
        status=new_status,
        message=f"Claim {payload.claim_id} {new_status.lower()} by {payload.agent_id}.",
    )


@router.get("/claims/pending")
async def get_pending_claims():
    """
    Return all AWAITING_REVIEW claims for the agent dashboard.

    Called by the Dashboard React page on load and on refresh.
    Returns newest claims first.
    """
    db = provide_db()
    claims = await db.get_claims_by_status("AWAITING_REVIEW")
    return {"claims": claims, "count": len(claims)}


@router.get("/claims/{claim_id}/images")
async def get_claim_images(claim_id: str):
    """
    Return image URLs for all photos uploaded for a claim.

    Scans data/uploads/{claim_id}/ on local disk and returns a list of
    image descriptors with URLs, filenames, and type (damage vs bag tag).

    Images are served via the /uploads StaticFiles mount in main.py.
    Dashboard ClaimCard fetches this on mount to display photos for review.

    Args:
        claim_id: The CLM-YYYYMMDD-XXXX claim identifier.

    Returns:
        JSON with 'images' list and 'count'.
        Each image has: url, filename, is_tag (bool).
        Returns empty list if no uploads found for this claim.
    """
    upload_dir = os.path.join("data", "uploads", claim_id)

    if not os.path.exists(upload_dir):
        logger.debug(
            "claim_images_dir_not_found",
            extra={"claim_id": claim_id, "path": upload_dir},
        )
        return {"images": [], "count": 0}

    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    images = []

    for filename in sorted(os.listdir(upload_dir)):
        if os.path.splitext(filename)[1].lower() in image_extensions:
            images.append(
                {
                    "url": f"/uploads/{claim_id}/{filename}",
                    "filename": filename,
                    "is_tag": "tag" in filename.lower(),
                }
            )

    logger.debug(
        "claim_images_fetched",
        extra={"claim_id": claim_id, "count": len(images)},
    )

    return {"images": images, "count": len(images)}
