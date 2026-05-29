from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.dependencies import provide_db

router = APIRouter(tags=["Agent Dashboard"])
logger = logging.getLogger(__name__)


class DecisionRequest(BaseModel):
    """Request body for the agent dashboard approve/reject action.

    Sent by the Dashboard React page when a staff member clicks Approve
    or Reject. agent_id is logged for audit purposes.
    """

    claim_id: str
    action: str  # "approve" | "reject"
    agent_id: str
    notes: Optional[str] = None
    modified_compensation: Optional[float] = None


class DecisionResponse(BaseModel):
    """Response returned after a staff decision is persisted.

    Returns the final compensation and voucher_code so the dashboard
    and polling simulator can update without a second fetch.
    """

    claim_id: str
    status: str
    message: str
    # Echoed back so the dashboard (and, via polling, the simulator) immediately
    # reflect the final persisted values without a second fetch.
    compensation: Optional[float] = None
    voucher_code: Optional[str] = None


def _generate_voucher() -> str:
    """Voucher code for an approved claim — same VCH-XXXXXXXX shape as Lane 1."""
    return f"VCH-{uuid.uuid4().hex[:8].upper()}"


@router.post("/decision", response_model=DecisionResponse)
async def agent_decision(payload: DecisionRequest) -> DecisionResponse:
    """
    Called by the Lane 2 agent dashboard when staff approve or reject a claim.

    approve → status RESOLVED, persists modified_compensation (if the agent
              edited it) and a freshly generated voucher_code.
    reject  → status REJECTED.

    All writes go to the DB in a SINGLE update so the edited compensation,
    voucher, and status are persisted together. The updated values are returned
    so the dashboard and the polling simulator both show the final amounts.

    No auth for POC — add JWT middleware in Phase 2.

    BUG FIX: all DB calls are now wrapped in try/except. A network error
    (e.g. [Errno 11001] getaddrinfo failed) previously caused an unhandled
    500 from FastAPI. Now returns a structured error DecisionResponse instead.
    """
    if payload.action not in ("approve", "reject"):
        return DecisionResponse(
            claim_id=payload.claim_id,
            status="error",
            message=f"Invalid action '{payload.action}'. Must be 'approve' or 'reject'.",
        )

    db = provide_db()

    if db is None:
        return DecisionResponse(
            claim_id=payload.claim_id,
            status="error",
            message="Database not configured — set SUPABASE_URL and "
                    "SUPABASE_SERVICE_ROLE_KEY in .env to enable claim persistence.",
        )

    # Look up the existing claim so we can fall back to its current compensation
    # when the agent did not edit the amount.
    try:
        existing = await db.get_claim(payload.claim_id)
    except Exception as exc:
        logger.warning(
            "agent_decision_db_get_failed",
            extra={"claim_id": payload.claim_id, "error": str(exc)},
        )
        return DecisionResponse(
            claim_id=payload.claim_id,
            status="error",
            message=(
                f"Could not reach the database to look up claim {payload.claim_id}. "
                "Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env."
            ),
        )

    if existing is None:
        return DecisionResponse(
            claim_id=payload.claim_id,
            status="error",
            message=f"Claim {payload.claim_id} not found.",
        )

    if payload.action == "approve":
        new_status = "RESOLVED"
        final_comp = (
            float(payload.modified_compensation)
            if payload.modified_compensation is not None
            else float(existing.get("compensation") or 0.0)
        )
        voucher = existing.get("voucher_code") or _generate_voucher()
        fields = {
            "status": new_status,
            "compensation": final_comp,
            "voucher_code": voucher,
        }
    else:  # reject
        new_status = "REJECTED"
        final_comp = float(existing.get("compensation") or 0.0)
        voucher = None
        fields = {"status": new_status}

    try:
        updated = await db.update_claim(payload.claim_id, fields)
    except Exception as exc:
        logger.warning(
            "agent_decision_db_update_failed",
            extra={"claim_id": payload.claim_id, "action": payload.action, "error": str(exc)},
        )
        return DecisionResponse(
            claim_id=payload.claim_id,
            status="error",
            message=(
                f"Decision recorded locally but could not be saved to the database. "
                f"Error: {exc}"
            ),
        )

    # Prefer the persisted values returned by the DB; fall back to what we set.
    if updated:
        final_comp = (
            float(updated.get("compensation"))
            if updated.get("compensation") is not None
            else final_comp
        )
        voucher = updated.get("voucher_code", voucher)

    logger.info(
        "agent_decision_completed",
        extra={
            "claim_id": payload.claim_id,
            "action": payload.action,
            "new_status": new_status,
            "agent_id": payload.agent_id,
            "compensation": final_comp,
            "voucher_code": voucher,
            "notes": payload.notes,
        },
    )

    return DecisionResponse(
        claim_id=payload.claim_id,
        status=new_status,
        message=f"Claim {payload.claim_id} {new_status.lower()} by {payload.agent_id}.",
        compensation=final_comp,
        voucher_code=voucher,
    )


@router.get("/claims/pending")
async def get_pending_claims():
    """
    Return all AWAITING_REVIEW claims for the agent dashboard.
    Called by the Dashboard React page on load and on refresh. Newest first.

    Returns an empty list if DB is not configured (missing Supabase credentials)
    so the dashboard renders cleanly instead of showing a backend error.

    BUG FIX: DB call is now wrapped in try/except. Previously a network error
    (e.g. [Errno 11001] getaddrinfo failed) caused FastAPI to return a 500,
    which the Dashboard caught as "Failed to load claims — is the backend
    running?". Now returns an empty list with a warning message instead.
    """
    db = provide_db()
    if db is None:
        return {
            "claims": [],
            "count": 0,
            "warning": "Database not configured — set SUPABASE_URL and "
                       "SUPABASE_SERVICE_ROLE_KEY in .env to enable claim persistence.",
        }

    try:
        claims = await db.get_claims_by_status("AWAITING_REVIEW")
        return {"claims": claims, "count": len(claims)}
    except Exception as exc:
        logger.warning(
            "get_pending_claims_db_failed",
            extra={"error": str(exc)},
        )
        return {
            "claims": [],
            "count": 0,
            "warning": (
                "Could not reach the database. "
                "Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env. "
                f"Error: {exc}"
            ),
        }


@router.get("/claims/{claim_id}/status")
async def get_claim_status(claim_id: str):
    """
    Lightweight status endpoint the simulator polls to learn the outcome of a
    Lane 2 claim after staff act in the dashboard.

    BUG FIX: DB call is now wrapped in try/except so a network error returns
    a structured response instead of a 500.
    """
    db = provide_db()
    if db is None:
        return {"found": False, "claim_id": claim_id}

    try:
        claim = await db.get_claim(claim_id)
    except Exception as exc:
        logger.warning(
            "get_claim_status_db_failed",
            extra={"claim_id": claim_id, "error": str(exc)},
        )
        return {"found": False, "claim_id": claim_id, "error": str(exc)}

    if claim is None:
        return {"found": False, "claim_id": claim_id}

    return {
        "found": True,
        "claim_id": claim_id,
        "status": claim.get("status"),
        "compensation": claim.get("compensation"),
        "voucher_code": claim.get("voucher_code"),
        "routing_lane": claim.get("routing_lane"),
    }


@router.get("/claims/{claim_id}/images")
async def get_claim_images(claim_id: str):
    """
    Return image URLs for all photos uploaded for a claim.

    Scans data/uploads/{claim_id}/ on local disk. Images are served via the
    /uploads StaticFiles mount in main.py. Dashboard ClaimCard fetches this on
    mount to display photos for review.
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