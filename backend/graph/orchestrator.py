from __future__ import annotations

import logging
from typing import Optional

from langgraph.graph import StateGraph, END

from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)


def _build_graph() -> StateGraph:
    """
    Wire the 5-agent pipeline as a LangGraph StateGraph.

    Adapted from Proj A LangGraphOrchestrator — same StateGraph pattern,
    linear A1→A2→A3→A4→conditional→A5 instead of intent-dispatch routing.

    Node stubs are imported lazily so missing implementations fail loudly at
    call time, not at import time (safe during early dev).
    """

    async def a1_node(state: ClaimState) -> ClaimState:
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

    async def a4_node(state: ClaimState) -> ClaimState:
        from backend.agents.a4_decision import A4DecisionAgent
        from backend.dependencies import provide_db
        return await A4DecisionAgent(db=provide_db()).handle(state, [])

    async def a5_node(state: ClaimState) -> ClaimState:
        from backend.agents.a5_notification import A5NotificationAgent
        return await A5NotificationAgent().handle(state, [])

    def _route_after_a4(state: ClaimState) -> str:
        """Conditional edge: after A4 always go to A5 (A5 handles both lanes)."""
        return "a5"

    graph = StateGraph(ClaimState)
    graph.add_node("a1", a1_node)
    graph.add_node("a2", a2_node)
    graph.add_node("a3", a3_node)
    graph.add_node("a4", a4_node)
    graph.add_node("a5", a5_node)

    graph.set_entry_point("a1")
    graph.add_edge("a1", "a2")
    graph.add_edge("a2", "a3")
    graph.add_edge("a3", "a4")
    graph.add_conditional_edges("a4", _route_after_a4, {"a5": "a5"})
    graph.add_edge("a5", END)

    return graph.compile()


# Compiled graph singleton — built once at startup
_chat_graph = None


def get_graph():
    global _chat_graph
    if _chat_graph is None:
        _chat_graph = _build_graph()
    return _chat_graph


class ClaimOrchestrator:
    """
    Entry point called by the webhook route.
    Adapted from Proj A LangGraphOrchestrator.
    """

    async def run(
        self,
        session_id: str,
        passenger_message: str,
        image_paths: list[str] | None = None,
        conversation_history: list | None = None,
        request_id: Optional[str] = None,
    ) -> ClaimState:

        state = ClaimState(
            session_id=session_id,
            passenger_message=passenger_message,
            image_paths=image_paths or [],
            conversation_history=conversation_history or [],
            request_id=request_id,
        )

        try:
            logger.info(
                "orchestration_started",
                extra={
                    "component": "ClaimOrchestrator",
                    "session_id": session_id,
                    "request_id": request_id,
                    "has_images": bool(image_paths),
                },
            )

            state = await get_graph().ainvoke(state)
            state.execution_completed = True
            logger.info("orchestration_completed", extra={"claim_id": state.claim_id, "lane": state.routing_lane})

        except Exception as e:
            logger.exception("orchestration_failed")
            state.set_error(str(e))

        return state
