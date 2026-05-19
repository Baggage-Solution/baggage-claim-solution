from __future__ import annotations

import logging
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
    (T-017)
    """
    db = provide_db()

    if payload.action not in ("approve", "reject"):
        return DecisionResponse(
            claim_id=payload.claim_id,
            status="error",
            message=f"Invalid action: {payload.action}",
        )

    new_status = "RESOLVED" if payload.action == "approve" else "REJECTED"

    # TODO (T-017):
    # 1. await db.update_claim_status(payload.claim_id, new_status)
    # 2. If approved: generate voucher, trigger A5 notification
    # 3. If modified_compensation: update claim record
    # 4. Log agent_id + action for audit trail

    logger.info(
        "agent_decision_received",
        extra={
            "claim_id": payload.claim_id,
            "action": payload.action,
            "agent": payload.agent_id,
        },
    )

    return DecisionResponse(
        claim_id=payload.claim_id,
        status=new_status,
        message=f"Claim {payload.claim_id} {new_status.lower()} by {payload.agent_id}.",
    )


@router.get("/claims/pending")
async def get_pending_claims():
    """Return all AWAITING_REVIEW claims for the agent dashboard. (T-017)"""
    # TODO (T-017): await db.get_claims_by_status("AWAITING_REVIEW")
    return {"claims": [], "count": 0}
