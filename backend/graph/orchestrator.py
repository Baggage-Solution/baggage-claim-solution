from __future__ import annotations

import logging
from typing import Optional

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

    WHY A2/A3 RUN BEFORE A1 ON IMAGE TURNS:
    A1 generates the passenger-facing reply. For image turns the reply must
    include what was found in the photos (damage types, severity, OCR data).
    Running A2→A3 first populates state fields that A1 then weaves into its
    response via the step prompt context injection.

    WHY conversation_step IS PASSED FROM FRONTEND:
    LangGraph MemorySaver does NOT persist plain dataclass field values between
    separate ainvoke() calls — input state overrides the checkpoint for fields
    without Annotated reducers. The frontend echoes the step it received from
    the last response back on the next request, making it the authoritative source.
    """

    async def router_node(state: ClaimState) -> ClaimState:
        """
        Stateless dispatch node — sets _route flag based on image presence.
        No LLM call here; just prepares routing decision for the conditional edge.
        """
        # Nothing to mutate; routing happens in the conditional edge function.
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
        """A1 for text-only turns (greeting, description, 'yes' at confirm)."""
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
        """
        A1 for image turns — runs AFTER A2+A3 so it can include damage
        assessment and OCR data in its passenger-facing reply.
        """
        from backend.agents.a1_conversation import A1ConversationAgent
        from backend.dependencies import provide_llm

        return await A1ConversationAgent(llm=provide_llm()).handle(state, [])

    async def a4_node(state: ClaimState) -> ClaimState:
        from backend.agents.a4_decision import A4DecisionAgent
        from backend.dependencies import provide_db

        return await A4DecisionAgent(db=provide_db()).handle(state, [])

    async def a5_node(state: ClaimState) -> ClaimState:
        from backend.agents.a5_notification import A5NotificationAgent

        return await A5NotificationAgent().handle(state, [])

    def _route_after_a1_image(state: ClaimState) -> str:
        """
        Run A4 only when BOTH damage AND tag images are present.
        A4 needs both to perform fraud checks and make the routing decision.
        """
        damage_paths = [p for p in state.image_paths if "tag" not in p.lower()]
        tag_paths = [p for p in state.image_paths if "tag" in p.lower()]

        if damage_paths and tag_paths:
            logger.info(
                "route_to_a4: full image set present",
                extra={
                    "session_id": state.session_id,
                    "damage_count": len(damage_paths),
                    "tag_count": len(tag_paths),
                },
            )
            return "a4"

        logger.info(
            "route_skip_a4: waiting for more images",
            extra={
                "session_id": state.session_id,
                "damage_count": len(damage_paths),
                "tag_count": len(tag_paths),
            },
        )
        return "end"

    def _route_after_a4(state: ClaimState) -> str:
        """Only proceed to A5 if A4 successfully set routing_lane."""
        if state.routing_lane in (1, 2):
            return "a5"
        logger.warning(
            "route_skip_a5: routing_lane not set",
            extra={"session_id": state.session_id, "lane": state.routing_lane},
        )
        return "end"

    # ── Build graph ───────────────────────────────────────────────────────────
    graph = StateGraph(ClaimState)

    graph.add_node("router", router_node)
    graph.add_node("a1_text", a1_text_node)
    graph.add_node("a2", a2_node)
    graph.add_node("a3", a3_node)
    graph.add_node("a1_image", a1_image_node)
    graph.add_node("a4", a4_node)
    graph.add_node("a5", a5_node)

    # Entry
    graph.add_edge(START, "router")

    # Router dispatch
    graph.add_conditional_edges(
        "router",
        _route_from_router,
        {"a1_text": "a1_text", "a2": "a2"},
    )

    # Text branch
    graph.add_edge("a1_text", END)

    # Image branch
    graph.add_edge("a2", "a3")
    graph.add_edge("a3", "a1_image")
    graph.add_conditional_edges(
        "a1_image",
        _route_after_a1_image,
        {"a4": "a4", "end": END},
    )
    graph.add_conditional_edges(
        "a4",
        _route_after_a4,
        {"a5": "a5", "end": END},
    )
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
        request_id: Optional[str] = None,
    ) -> ClaimState:
        """
        Run the agent pipeline for one passenger turn.

        conversation_step is injected from the frontend because LangGraph
        MemorySaver does not persist plain dataclass fields across separate
        ainvoke() calls — the frontend echoes the step from the last response.
        """
        state = ClaimState(
            session_id=session_id,
            passenger_message=passenger_message,
            image_paths=image_paths or [],
            conversation_history=conversation_history or [],
            conversation_step=conversation_step,
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
