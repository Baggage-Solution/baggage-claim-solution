from __future__ import annotations

import logging
from typing import List, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

_checkpointer: MemorySaver = MemorySaver()


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
        from backend.agents.a1_conversation import A1ConversationAgent
        from backend.dependencies import provide_llm
        return await A1ConversationAgent(llm=provide_llm()).handle(state, [])

    async def a2_node(state: ClaimState) -> ClaimState:
        from backend.agents.a2_vision import A2VisionAgent
        from backend.dependencies import provide_vision
        return await A2VisionAgent(vision=provide_vision()).handle(state, [])

    async def a3_node(state: ClaimState) -> ClaimState:
        from backend.agents.a3_ocr import A3OCRAgent
        from backend.dependencies import provide_ocr
        return await A3OCRAgent(ocr=provide_ocr()).handle(state, [])

    async def a1_image_node(state: ClaimState) -> ClaimState:
        from backend.agents.a1_conversation import A1ConversationAgent
        from backend.dependencies import provide_llm
        return await A1ConversationAgent(llm=provide_llm()).handle(state, [])

    async def a4_node(state: ClaimState) -> ClaimState:
        from backend.agents.a4_decision import A4DecisionAgent
        from backend.dependencies import provide_db
        return await A4DecisionAgent(db=provide_db()).handle(state, [])

    async def a5_node(state: ClaimState) -> ClaimState:
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
        has_both = bool(damage_paths and tag_paths)
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
    graph.add_conditional_edges("router", _route_from_router, {"a1_text": "a1_text", "a2": "a2"})
    graph.add_edge("a1_text", END)
    graph.add_edge("a2", "a3")
    graph.add_edge("a3", "a1_image")
    graph.add_conditional_edges("a1_image", _route_after_a1_image, {"a4": "a4", "end": END})
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
    global _chat_graph
    if _chat_graph is None:
        _chat_graph = _build_graph()
    return _chat_graph


class ClaimOrchestrator:

    async def run(
        self,
        session_id: str,
        passenger_message: str,
        image_paths: list[str] | None = None,
        conversation_history: list | None = None,
        conversation_step: str = "greeting",
        conversation_ended: bool = False,
        # A2 echoed results
        processed_damage_paths: list[str] | None = None,
        damage_types: list[str] | None = None,
        severity_score: float = 0.0,
        brand_detected: str | None = None,
        is_luxury: bool = False,
        compensation_estimate_usd: float = 0.0,
        # A3 echoed results
        flight_number: str | None = None,
        pnr: str | None = None,
        bag_id: str | None = None,
        ocr_confidence: float = 0.0,
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
            # Seed A2 results from echoed frontend state
            conversation_ended=conversation_ended,
            processed_damage_paths=processed_damage_paths or [],
            damage_types=damage_types or [],
            severity_score=severity_score,
            brand_detected=brand_detected,
            is_luxury=is_luxury,
            compensation_estimate_usd=compensation_estimate_usd,
            # Seed A3 results from echoed frontend state
            flight_number=flight_number,
            pnr=pnr,
            bag_id=bag_id,
            ocr_confidence=ocr_confidence,
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