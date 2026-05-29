from __future__ import annotations

import logging
import os
import shutil
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

_checkpointer: MemorySaver = MemorySaver()


def _move_pending_uploads(claim_id: str) -> None:
    """
    Move uploaded photos from data/uploads/pending/ → data/uploads/{claim_id}/
    after A4 has finalized the claim and assigned a claim_id.

    Why this is needed:
    Photos are uploaded before the claim_id exists (passenger uploads during
    the conversation, A4 generates the claim_id only at the end). The storage
    provider saves them under data/uploads/pending/ as a staging area.
    Once the claim is finalized, files must live under the claim_id folder
    so GET /claims/{claim_id}/images can find and serve them to the dashboard.

    Phase 2 swap: replace local shutil.move with R2/S3 copy + delete calls.
    The claim_id is available at this point so the destination key is known.

    Args:
        claim_id: The CLM-YYYYMMDD-XXXX identifier assigned by A4.
    """
    pending_dir = os.path.join("data", "uploads", "pending")
    claim_dir = os.path.join("data", "uploads", claim_id)

    if not os.path.exists(pending_dir):
        logger.debug(
            "pending_uploads_dir_not_found",
            extra={"pending_dir": pending_dir},
        )
        return

    files = [
        f
        for f in os.listdir(pending_dir)
        if os.path.isfile(os.path.join(pending_dir, f))
    ]

    if not files:
        logger.debug("pending_uploads_empty", extra={"claim_id": claim_id})
        return

    os.makedirs(claim_dir, exist_ok=True)

    moved = []
    for filename in files:
        src = os.path.join(pending_dir, filename)
        dst = os.path.join(claim_dir, filename)
        shutil.move(src, dst)
        moved.append(filename)

    logger.info(
        "uploads_moved_to_claim",
        extra={
            "claim_id": claim_id,
            "count": len(moved),
            "files": moved,
            "src": pending_dir,
            "dst": claim_dir,
        },
    )


def _build_graph() -> StateGraph:
    """
    Wire the 5-agent pipeline as a LangGraph StateGraph.

    Graph shape
    -----------
                         ┌─ a2 → a3 → a1_image → [a4 → [a5→END | END] | END]
    START → router ──────┤
                         └─ a1_text → END
    """

    async def router_node(state: ClaimState) -> ClaimState:
        """Entry node — pass-through that triggers the conditional router."""
        return state

    def _route_from_router(state: ClaimState) -> str:
        if state.image_paths:
            logger.info(
                "router: images present → image pipeline",
                extra={
                    "session_id": state.session_id,
                    "image_count": len(state.image_paths),
                    "step": state.conversation_step,
                },
            )
            return "a2"
        logger.info(
            "router: no images → text branch",
            extra={"session_id": state.session_id, "step": state.conversation_step},
        )
        return "a1_text"

    async def a1_text_node(state: ClaimState) -> ClaimState:
        """Text-only branch node — runs A1 with no image context."""
        from backend.agents.a1_conversation import A1ConversationAgent
        from backend.dependencies import provide_llm

        return await A1ConversationAgent(llm=provide_llm()).handle(state, [])

    async def a2_node(state: ClaimState) -> ClaimState:
        """Image branch — runs A2 vision analysis on uploaded damage photos."""
        from backend.agents.a2_vision import A2VisionAgent
        from backend.dependencies import provide_vision

        return await A2VisionAgent(vision=provide_vision()).handle(state, [])

    async def a3_node(state: ClaimState) -> ClaimState:
        """Image branch — runs A3 OCR on bag tag photos and tag candidates."""
        from backend.agents.a3_ocr import A3OCRAgent
        from backend.dependencies import provide_ocr

        return await A3OCRAgent(ocr=provide_ocr()).handle(state, [])

    async def a1_image_node(state: ClaimState) -> ClaimState:
        """Image branch — runs A1 AFTER A2/A3 to reply using analysed data."""
        from backend.agents.a1_conversation import A1ConversationAgent
        from backend.dependencies import provide_llm

        return await A1ConversationAgent(llm=provide_llm()).handle(state, [])

    async def a4_node(state: ClaimState) -> ClaimState:
        """Image branch — runs A4 decision engine after confirm step."""
        from backend.agents.a4_decision import A4DecisionAgent
        from backend.dependencies import provide_db

        return await A4DecisionAgent(db=provide_db()).handle(state, [])

    async def a5_node(state: ClaimState) -> ClaimState:
        """Image branch — runs A5 notification after A4 routing decision."""
        from backend.agents.a5_notification import A5NotificationAgent
        from backend.dependencies import provide_db

        return await A5NotificationAgent(db=provide_db()).handle(state, [])

    def _route_after_a1_image(state: ClaimState) -> str:
        """
        Route to A4 only when:
        1. Both damage AND tag images are present.
        2. A1 has advanced step to "result" — meaning the passenger confirmed.

        On the tag_photo turn: A1 advances tag_photo → confirm (routing_lane still None).
        step="confirm" → skip A4. Passenger still needs to type "yes".

        On the confirm turn: A1 advances confirm → result.
        step="result" → run A4. Claim is processed.
        """
        damage_paths = [p for p in state.image_paths if "tag" not in p.lower()]
        tag_paths = [p for p in state.image_paths if "tag" in p.lower()]
        # Tag data can come from a dedicated tag photo, a tag spotted inside a
        # damage photo (issue #2/#4), or manual entry (issue #3). Any of these
        # counts as "we have the tag side of the claim".
        have_tag_data = bool(
            tag_paths or state.tag_data_complete or state.flight_number or state.bag_id
        )
        has_both = bool(damage_paths and have_tag_data)
        passenger_confirmed = state.conversation_step == "result"

        if has_both and passenger_confirmed:
            logger.info(
                "route_to_a4: full image set + passenger confirmed",
                extra={
                    "session_id": state.session_id,
                    "damage_count": len(damage_paths),
                    "tag_count": len(tag_paths),
                    "conversation_step": state.conversation_step,
                },
            )
            return "a4"

        logger.info(
            "route_skip_a4: waiting for confirmation or more images",
            extra={
                "session_id": state.session_id,
                "has_both": has_both,
                "passenger_confirmed": passenger_confirmed,
                "conversation_step": state.conversation_step,
            },
        )
        return "end"

    def _route_after_a4(state: ClaimState) -> str:
        if state.routing_lane in (1, 2):
            return "a5"
        logger.warning(
            "route_skip_a5: routing_lane not set",
            extra={"session_id": state.session_id, "lane": state.routing_lane},
        )
        return "end"

    graph = StateGraph(ClaimState)

    graph.add_node("router", router_node)
    graph.add_node("a1_text", a1_text_node)
    graph.add_node("a2", a2_node)
    graph.add_node("a3", a3_node)
    graph.add_node("a1_image", a1_image_node)
    graph.add_node("a4", a4_node)
    graph.add_node("a5", a5_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router", _route_from_router, {"a1_text": "a1_text", "a2": "a2"}
    )
    graph.add_edge("a1_text", END)
    graph.add_edge("a2", "a3")
    graph.add_edge("a3", "a1_image")
    graph.add_conditional_edges(
        "a1_image", _route_after_a1_image, {"a4": "a4", "end": END}
    )
    graph.add_conditional_edges("a4", _route_after_a4, {"a5": "a5", "end": END})
    graph.add_edge("a5", END)

    compiled = graph.compile(checkpointer=_checkpointer)
    logger.info(
        "graph_compiled",
        extra={
            "text_branch": "router→a1_text→END",
            "image_branch": "router→a2→a3→a1_image→[a4→[a5→END|END]|END]",
        },
    )
    return compiled


_chat_graph = None


def get_graph():
    """Return the compiled LangGraph StateGraph (singleton).

    Builds the graph on first call and caches it globally. The graph
    encodes the full 5-agent pipeline: router → A2/A3/A1_image/A4/A5 or
    router → A1_text, depending on whether the turn has image uploads.

    Returns:
        CompiledStateGraph: The compiled LangGraph graph ready to invoke.
    """
    global _chat_graph
    if _chat_graph is None:
        _chat_graph = _build_graph()
    return _chat_graph


class ClaimOrchestrator:
    """Thin facade over the compiled LangGraph graph.

    Translates flat webhook parameters into a ClaimState, invokes the graph
    for one passenger turn, and returns the updated state for the caller to
    persist and return to the simulator.

    Agents are never imported here directly — they are resolved at runtime
    by the graph node functions which call provide_llm / provide_vision etc.
    """

    async def run(
        self,
        session_id: str,
        passenger_message: str,
        image_paths: list[str] | None = None,
        conversation_history: list | None = None,
        conversation_step: str = "greeting",
        conversation_ended: bool = False,
        no_damage_detected: bool = False,
        # Issue #1 — object gate
        not_a_bag: bool = False,
        last_object_description: str | None = None,
        non_bag_attempts: int = 0,
        # Issue #2/#4 — tag in damage photo
        tag_in_damage_photo: bool = False,
        tag_candidate_paths: list[str] | None = None,
        # A2 echoed results
        processed_damage_paths: list[str] | None = None,
        damage_types: list[str] | None = None,
        severity_score: float = 0.0,
        brand_detected: str | None = None,
        is_luxury: bool = False,
        compensation_estimate_usd: float = 0.0,
        # A3 echoed results
        processed_tag_paths: list[str] | None = None,
        flight_number: str | None = None,
        pnr: str | None = None,
        bag_id: str | None = None,
        ocr_confidence: float = 0.0,
        tag_data_complete: bool = False,
        tag_manually_entered: bool = False,
        # Issue #3 — manual tag entry
        manual_tag_text: str | None = None,
        manual_flight_number: str | None = None,
        manual_pnr: str | None = None,
        manual_bag_id: str | None = None,
        offer_manual_entry: bool = False,
        request_id: Optional[str] = None,
    ) -> ClaimState:
        """
        Run the agent pipeline for one passenger turn.

        A2 and A3 results are echoed back from the frontend on every request
        because LangGraph MemorySaver does not persist plain dataclass fields
        between separate ainvoke() calls. Without this, the confirm turn would
        start with blank damage_types/severity/compensation and A4 would always
        see $0 compensation → always route to Lane 1 regardless of actual damage.
        """
        state = ClaimState(
            session_id=session_id,
            passenger_message=passenger_message,
            image_paths=image_paths or [],
            conversation_history=conversation_history or [],
            conversation_step=conversation_step,
            conversation_ended=conversation_ended,
            no_damage_detected=no_damage_detected,
            # Issue #1 — object gate
            not_a_bag=not_a_bag,
            last_object_description=last_object_description,
            non_bag_attempts=non_bag_attempts,
            # Issue #2/#4 — tag in damage photo
            tag_in_damage_photo=tag_in_damage_photo,
            tag_candidate_paths=tag_candidate_paths or [],
            # Seed A2 results from echoed frontend state
            processed_damage_paths=processed_damage_paths or [],
            damage_types=damage_types or [],
            severity_score=severity_score,
            brand_detected=brand_detected,
            is_luxury=is_luxury,
            compensation_estimate_usd=compensation_estimate_usd,
            # Seed A3 results from echoed frontend state
            processed_tag_paths=processed_tag_paths or [],
            flight_number=flight_number,
            pnr=pnr,
            bag_id=bag_id,
            ocr_confidence=ocr_confidence,
            tag_data_complete=tag_data_complete,
            tag_manually_entered=tag_manually_entered,
            # Issue #3 — manual tag entry
            manual_tag_text=manual_tag_text,
            manual_flight_number=manual_flight_number,
            manual_pnr=manual_pnr,
            manual_bag_id=manual_bag_id,
            offer_manual_entry=offer_manual_entry,
            request_id=request_id,
        )

        config = {"configurable": {"thread_id": session_id}}

        try:
            logger.info(
                "orchestration_started",
                extra={
                    "session_id": session_id,
                    "request_id": request_id,
                    "conversation_step": conversation_step,
                    "image_count": len(image_paths or []),
                    "seeded_severity": severity_score,
                    "seeded_compensation": compensation_estimate_usd,
                },
            )

            result = await get_graph().ainvoke(state, config=config)

            if not isinstance(result, ClaimState):
                state = ClaimState(
                    **{
                        k: v
                        for k, v in result.items()
                        if k in ClaimState.__dataclass_fields__
                    }
                )
            else:
                state = result

            # ── Move pending uploads to claim folder ──────────────────────────
            # A4 assigns claim_id during this run. Photos were stored under
            # data/uploads/pending/ because the claim_id wasn't known at upload
            # time. Now that we have it, move files to data/uploads/{claim_id}/
            # so GET /claims/{claim_id}/images finds them on the dashboard.
            if state.claim_id:
                _move_pending_uploads(state.claim_id)

            state.execution_completed = True

            logger.info(
                "orchestration_completed",
                extra={
                    "claim_id": state.claim_id,
                    "lane": state.routing_lane,
                    "conversation_step": state.conversation_step,
                },
            )

        except Exception as e:
            logger.exception("orchestration_failed")
            state.set_error(str(e))

        return state
