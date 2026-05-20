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
    Agent A1 — Passenger Conversation.

    Responsibilities:
    - Detect conversation step from session state.
    - Generate empathetic multilingual passenger-facing responses.
    - Set re_request_tag / re_request_damage flags when retries needed.
    - Advance conversation_step after each successful exchange.

    Provider: LLMProvider (injected — never import Gemini directly here).
    Prompt file: backend/prompts/a1_conversation.json
    """

    def __init__(self, llm) -> None:
        """
        Initialise A1 conversation agent.

        Args:
            llm: LLMProvider instance (injected from dependencies.py).
        """
        super().__init__(
            name="a1_conversation",
            description="Passenger conversation agent",
        )
        self._llm = llm

    def _get_step_prompt(self, state: ClaimState, prompts: dict) -> str:
        """
        Determine the correct prompt template based on current conversation state.

        Priority order:
        1. re_request_tag — bag tag photo was unclear, ask to retake
        2. re_request_damage — damage photos were unclear, ask to retake
        3. result_lane1 / result_lane2 — claim decision made
        4. current conversation_step — normal flow

        Args:
            state: Current ClaimState with conversation context.
            prompts: Loaded a1_conversation.json steps dict.

        Returns:
            Prompt string for the current step.
        """
        steps = prompts.get("steps", {})

        # Retry requests take highest priority
        if state.re_request_tag:
            return steps.get("re_request_tag", "")

        if state.re_request_damage:
            return steps.get("re_request_damage", "")

        # Result step — branch by lane
        if state.conversation_step == "result":
            if state.routing_lane == 1:
                return PromptLoader.render(
                    steps.get("result_lane1", ""),
                    {
                        "voucher_code": state.voucher_code or "N/A",
                        "compensation": f"{state.final_compensation_usd:.2f}",
                    },
                )
            else:
                return PromptLoader.render(
                    steps.get("result_lane2", ""),
                    {"claim_id": state.claim_id or "N/A"},
                )

        # Normal flow — use current step
        return steps.get(state.conversation_step, steps.get("greeting", ""))

    def _build_messages(
        self, state: ClaimState, step_prompt: str, system_prompt: str
    ) -> List[dict]:
        """
        Build the full message list to send to the LLM.

        Includes system prompt, conversation history, and
        the current step instruction as a user message.

        Args:
            state: Current ClaimState.
            step_prompt: Step-specific instruction from prompt template.
            system_prompt: System-level persona prompt from a1_conversation.json.

        Returns:
            List of {role, content} dicts ready for LLMProvider.chat().
        """
        messages = [{"role": "system", "content": system_prompt}]

        # Include last 6 turns of conversation history for context window
        if state.conversation_history:
            messages.extend(state.conversation_history[-6:])

        # Add passenger's latest message
        if state.passenger_message:
            messages.append({"role": "user", "content": state.passenger_message})

        # Append step instruction as additional context
        if step_prompt:
            messages.append(
                {
                    "role": "user",
                    "content": f"[INSTRUCTION — do not repeat this to the passenger]: {step_prompt}",
                }
            )

        return messages

    def _advance_step(self, state: ClaimState) -> str:
        """
        Advance the conversation step to the next one in the flow.

        Does not advance if:
        - We are in a retry state (re_request_tag or re_request_damage)
        - We have already reached 'result'
        - A4 has not set routing_lane yet (claim not decided)

        Args:
            state: Current ClaimState.

        Returns:
            Next conversation step string.
        """
        if state.re_request_tag or state.re_request_damage:
            return state.conversation_step

        if state.conversation_step == "result":
            return "result"

        # If A4 has made a decision, jump to result
        if state.routing_lane is not None:
            return "result"

        current_index = (
            STEPS.index(state.conversation_step)
            if state.conversation_step in STEPS
            else 0
        )
        next_index = min(current_index + 1, len(STEPS) - 1)
        return STEPS[next_index]

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        """
        Process current conversation state and generate passenger response.

        Detects conversation step, builds prompt with history,
        calls LLM, sets a1_response, and advances conversation step.

        Args:
            state: Current ClaimState flowing through LangGraph pipeline.
            tasks: Unused — kept for BaseAgent interface compatibility.

        Returns:
            Updated ClaimState with a1_response and advanced conversation_step.
        """
        logger.info(
            "a1_started",
            extra={
                "component": "A1",
                "step": state.conversation_step,
                "session_id": state.session_id,
                "re_request_tag": state.re_request_tag,
                "re_request_damage": state.re_request_damage,
            },
        )

        try:
            # Load prompt template from JSON
            prompts = PromptLoader.load("a1_conversation")
            system_prompt = prompts.get(
                "system", "You are a helpful airline assistant."
            )

            # Determine which step prompt to use
            step_prompt = self._get_step_prompt(state, prompts)

            # Build full message list
            messages = self._build_messages(state, step_prompt, system_prompt)

            # Call LLM
            reply = await self._llm.chat(messages, temperature=0.3)

            # Update state
            state.a1_response = reply
            state.conversation_step = self._advance_step(state)

            state.add_debug("a1_step", state.conversation_step)
            state.add_debug("a1_reply_length", len(reply))

            logger.info(
                "a1_completed",
                extra={
                    "component": "A1",
                    "next_step": state.conversation_step,
                    "reply_length": len(reply),
                },
            )

        except Exception as exc:
            logger.exception("a1_failed")
            state.set_error(f"A1 error: {exc}")

        return state
