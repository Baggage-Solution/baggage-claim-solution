from __future__ import annotations

import logging
import uuid
from typing import List

from backend.agents.base_agent import BaseAgent
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)


class A5NotificationAgent(BaseAgent):
    """
    Agent A5 — Notification.

    Lane 1 (auto-approve):
    - Generate voucher code.
    - Simulate WhatsApp send (POC: write to event queue for simulator UI to pick up).
    - Set state.voucher_code and notification_sent = True.

    Lane 2 (staff review):
    - Push claim to HITL queue (Supabase claims table with status=AWAITING_REVIEW).
    - Set state.hitl_queued = True.
    - LangGraph interrupt() stub for real HITL in Phase 2.

    POC: WhatsApp send is simulated by returning the message in ClaimState.
    Production: swap simulator push for Meta Cloud API call.
    """

    def __init__(self) -> None:
        super().__init__(name="a5_notification", description="Notification and HITL routing agent")

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        logger.info("a5_started", extra={"component": "A5", "lane": state.routing_lane})

        try:
            if state.routing_lane == 1:
                await self._handle_lane1(state)
            elif state.routing_lane == 2:
                await self._handle_lane2(state)
            else:
                logger.warning("a5_unknown_lane", extra={"lane": state.routing_lane})

        except Exception as exc:
            logger.exception("a5_failed")
            state.set_error(f"A5 error: {exc}")

        logger.info("a5_completed", extra={"component": "A5", "notified": state.notification_sent})
        return state

    async def _handle_lane1(self, state: ClaimState) -> None:
        """Auto-approve: generate voucher, simulate send."""
        state.voucher_code = f"VCH-{uuid.uuid4().hex[:8].upper()}"
        state.notification_sent = True
        state.conversation_step = "result"

        # TODO (T-015): push approval message + voucher to simulator event queue
        # In production: POST to Meta Cloud API
        # msg = f"Your claim {state.claim_id} is approved! Voucher: {state.voucher_code}"

        logger.info("a5_lane1_approved", extra={"claim_id": state.claim_id, "voucher": state.voucher_code})

    async def _handle_lane2(self, state: ClaimState) -> None:
        """Staff review: push to HITL queue."""
        state.hitl_queued = True
        state.conversation_step = "result"

        # TODO (T-015 + T-014):
        # await db.update_claim_status(state.claim_id, "AWAITING_REVIEW")
        # In production: LangGraph interrupt() pauses graph here until agent dashboard action

        logger.info("a5_lane2_queued", extra={"claim_id": state.claim_id})
