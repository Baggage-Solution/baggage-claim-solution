from __future__ import annotations

import logging
from typing import List

from backend.agents.base_agent import BaseAgent
from backend.core.prompt_loader import PromptLoader
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

# Conversation steps in order
STEPS = ["greeting", "damage_photos", "tag_photo", "confirm", "result"]


class A1ConversationAgent(BaseAgent):
    """
    Agent A1 — Conversation.

    Responsibilities:
    - Detect conversation step from session state.
    - Generate empathetic multilingual passenger-facing responses.
    - Set re_request_tag / re_request_damage flags when retries needed.
    - Advance conversation_step after each successful exchange.

    Provider: LLMProvider (injected — never import Gemini directly here).
    Prompt file: backend/prompts/a1_conversation.json
    """

    def __init__(self, llm) -> None:
        super().__init__(name="a1_conversation", description="Passenger conversation agent")
        self._llm = llm  # LLMProvider instance

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        logger.info("a1_started", extra={"component": "A1", "step": state.conversation_step})

        try:
            # TODO (T-008): implement conversation logic
            # Steps:
            # 1. Detect current conversation step from state.conversation_step
            # 2. Build prompt using PromptLoader.load("a1_conversation")
            # 3. Call self._llm.chat(messages) → response text
            # 4. Set state.a1_response = response
            # 5. Advance state.conversation_step to next step if appropriate
            # 6. Set state.re_request_tag = True if A3 flagged low confidence

            state.a1_response = "[A1 stub] Hello! Please describe and photograph the damage."
            state.add_debug("a1_step", state.conversation_step)

        except Exception as exc:
            logger.exception("a1_failed")
            state.set_error(f"A1 error: {exc}")

        logger.info("a1_completed", extra={"component": "A1"})
        return state
