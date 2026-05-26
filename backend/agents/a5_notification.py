from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.agents.base_agent import BaseAgent
from backend.core.prompt_loader import PromptLoader
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

# Global SSE event queue — simulator polls this for real-time updates
# Key: session_id, Value: asyncio.Queue of event dicts
_sse_queues: Dict[str, asyncio.Queue] = {}


def get_or_create_queue(session_id: str) -> asyncio.Queue:
    """
    Get or create an SSE event queue for a session.

    Each simulator session has its own queue. Events are pushed
    by A5 and consumed by the /events/{session_id} SSE endpoint.

    Args:
        session_id: Unique session identifier from the simulator.

    Returns:
        asyncio.Queue for this session.
    """
    if session_id not in _sse_queues:
        _sse_queues[session_id] = asyncio.Queue()
    return _sse_queues[session_id]


def get_all_queues() -> Dict[str, asyncio.Queue]:
    """
    Return all active SSE queues.

    Used by the SSE endpoint to look up queues by session_id.

    Returns:
        Dict mapping session_id to asyncio.Queue.
    """
    return _sse_queues


class A5NotificationAgent(BaseAgent):
    """
    Agent A5 — Notification and HITL routing.

    Lane 1 (auto-approve):
    - Generate voucher code (VCH-XXXXXXXX).
    - Update claim status to APPROVED in Supabase.
    - Push approval event to SSE queue → simulator shows voucher card.
    - Set state.notification_sent = True.

    Lane 2 (staff review):
    - Update claim status to AWAITING_REVIEW in Supabase.
    - Push pending event to SSE queue → simulator shows 'Under Review' card.
    - Set state.hitl_queued = True.

    POC: WhatsApp send is simulated via SSE event stream.
    Production: swap SSE push for Meta Cloud API POST.
    LangGraph interrupt() for real HITL is Phase 2.

    Provider: DBProvider (injected — never import Supabase directly here).
    """

    def __init__(self, db=None) -> None:
        """
        Initialise A5 notification agent.

        Args:
            db: DBProvider instance (injected from dependencies.py).
                Optional for backward compatibility with existing tests.
        """
        super().__init__(
            name="a5_notification",
            description="Notification and HITL routing agent",
        )
        self._db = db

    async def _push_sse_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """
        Push an event to the SSE queue for a simulator session.

        Events are consumed by the GET /events/{session_id} endpoint
        and streamed to the React simulator as Server-Sent Events.

        Args:
            session_id: Target simulator session.
            event: Dict with 'type' and payload fields.
                   e.g. {'type': 'lane1_result', 'voucher_code': 'VCH-XXXX'}
        """
        queue = get_or_create_queue(session_id)
        await queue.put(event)
        logger.info(
            "sse_event_pushed",
            extra={
                "session_id": session_id,
                "event_type": event.get("type"),
            },
        )

    async def _handle_lane1(self, state: ClaimState) -> None:
        """
        Auto-approve flow: generate voucher, update DB, push SSE event.

        Steps:
        1. Generate voucher code VCH-XXXXXXXX.
        2. Update claim status to APPROVED in Supabase.
        3. Load lane1_message from a5_notification.json prompt.
        4. Push lane1_result SSE event with voucher to simulator.
        5. Set notification_sent = True.

        Args:
            state: Current ClaimState. Modifies voucher_code,
                   notification_sent, conversation_step in place.
        """
        # Step 1 — generate voucher
        state.voucher_code = f"VCH-{uuid.uuid4().hex[:8].upper()}"
        state.notification_sent = True
        state.conversation_step = "result"

        # Step 2 — update claim status in DB
        if self._db and state.claim_id:
            try:
                await self._db.update_claim_status(state.claim_id, "APPROVED")
                logger.info(
                    "a5_db_status_updated",
                    extra={"claim_id": state.claim_id, "status": "APPROVED"},
                )
            except Exception as exc:
                logger.warning(
                    "a5_db_update_failed — continuing",
                    extra={"claim_id": state.claim_id, "error": str(exc)},
                )

        # Step 3 — load notification message from prompt template
        try:
            prompts = PromptLoader.load("a5_notification")
            message = PromptLoader.render(
                prompts.get("lane1_message", ""),
                {
                    "claim_id": state.claim_id or "N/A",
                    "compensation": f"{state.final_compensation_usd:.2f}",
                    "voucher_code": state.voucher_code,
                },
            )
        except Exception:
            message = (
                f"Your claim is approved! "
                f"Voucher: {state.voucher_code}. "
                f"Compensation: ${state.final_compensation_usd:.2f}"
            )

        # Step 4 — push SSE event to simulator
        await self._push_sse_event(
            state.session_id,
            {
                "type": "lane1_result",
                "claim_id": state.claim_id,
                "voucher_code": state.voucher_code,
                "compensation": state.final_compensation_usd,
                "message": message,
            },
        )

        logger.info(
            "a5_lane1_approved",
            extra={
                "claim_id": state.claim_id,
                "voucher": state.voucher_code,
                "compensation": state.final_compensation_usd,
            },
        )

    async def _handle_lane2(self, state: ClaimState) -> None:
        """
        Staff review flow: update DB to AWAITING_REVIEW, push SSE event.

        Steps:
        1. Update claim status to AWAITING_REVIEW in Supabase.
        2. Load lane2_message from a5_notification.json prompt.
        3. Push lane2_result SSE event to simulator → shows 'Under Review' card.
        4. Set hitl_queued = True.

        Args:
            state: Current ClaimState. Modifies hitl_queued,
                   conversation_step in place.
        """
        state.hitl_queued = True
        state.conversation_step = "result"

        # Step 1 — update claim status in DB
        if self._db and state.claim_id:
            try:
                await self._db.update_claim_status(state.claim_id, "AWAITING_REVIEW")
                logger.info(
                    "a5_db_status_updated",
                    extra={
                        "claim_id": state.claim_id,
                        "status": "AWAITING_REVIEW",
                    },
                )
            except Exception as exc:
                logger.warning(
                    "a5_db_update_failed — continuing",
                    extra={"claim_id": state.claim_id, "error": str(exc)},
                )

        # Step 2 — load notification message
        try:
            prompts = PromptLoader.load("a5_notification")
            message = PromptLoader.render(
                prompts.get("lane2_message", ""),
                {"claim_id": state.claim_id or "N/A"},
            )
        except Exception:
            message = (
                f"Your claim {state.claim_id} has been submitted for review. "
                f"Our team will contact you within 24 hours."
            )

        # Step 3 — push SSE event to simulator
        await self._push_sse_event(
            state.session_id,
            {
                "type": "lane2_result",
                "claim_id": state.claim_id,
                "message": message,
            },
        )

        logger.info(
            "a5_lane2_queued",
            extra={"claim_id": state.claim_id},
        )

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        """
        Route claim to Lane 1 or Lane 2 and send notification.

        Args:
            state: Current ClaimState from LangGraph pipeline.
            tasks: Unused — kept for BaseAgent interface compatibility.

        Returns:
            Updated ClaimState with notification_sent or hitl_queued set.
        """
        logger.info(
            "a5_started",
            extra={
                "component": "A5",
                "lane": state.routing_lane,
                "claim_id": state.claim_id,
            },
        )

        try:
            if state.routing_lane == 1:
                await self._handle_lane1(state)
            elif state.routing_lane == 2:
                await self._handle_lane2(state)
            else:
                logger.warning(
                    "a5_unknown_lane",
                    extra={"lane": state.routing_lane},
                )

        except Exception as exc:
            logger.exception("a5_failed")
            state.set_error(f"A5 error: {exc}")

        logger.info(
            "a5_completed",
            extra={
                "component": "A5",
                "notified": state.notification_sent,
                "hitl_queued": state.hitl_queued,
            },
        )
        return state
