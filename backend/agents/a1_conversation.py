from __future__ import annotations

import logging
from typing import List

from backend.agents.base_agent import BaseAgent
from backend.core.prompt_loader import PromptLoader
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

STEPS = ["greeting", "damage_photos", "tag_photo", "confirm", "result"]


class A1ConversationAgent(BaseAgent):
    """
    Agent A1 — Passenger Conversation.

    On image turns A1 runs AFTER A2 and A3 (see orchestrator.py), so state
    already has damage_types, severity_score, brand_detected, flight_number
    etc. populated when A1 builds its LLM messages.

    Provider: LLMProvider (injected).
    Prompt file: backend/prompts/a1_conversation.json
    """

    def __init__(self, llm) -> None:
        super().__init__(
            name="a1_conversation", description="Passenger conversation agent"
        )
        self._llm = llm

    def _build_analysis_context(self, state: ClaimState) -> str:
        parts = []

        if state.damage_types:
            parts.append(f"- Damage types detected: {', '.join(state.damage_types)}")
        if state.severity_score > 0:
            severity_label = (
                "minor"
                if state.severity_score < 0.35
                else (
                    "moderate"
                    if state.severity_score < 0.65
                    else "severe" if state.severity_score < 0.9 else "total loss"
                )
            )
            parts.append(
                f"- Damage severity: {severity_label} ({state.severity_score:.0%})"
            )
        if state.brand_detected:
            luxury_note = (
                " (luxury brand — 1.5× compensation applies)" if state.is_luxury else ""
            )
            parts.append(f"- Bag brand: {state.brand_detected}{luxury_note}")
        if state.compensation_estimate_usd > 0:
            parts.append(
                f"- Estimated compensation: ${state.compensation_estimate_usd:.2f} USD"
            )
        if state.flight_number:
            parts.append(f"- Flight number from tag: {state.flight_number}")
        if state.pnr:
            parts.append(f"- PNR from tag: {state.pnr}")
        if state.bag_id:
            parts.append(f"- Bag ID from tag: {state.bag_id}")
        if state.ocr_confidence > 0 and not state.flight_number and not state.pnr:
            parts.append(
                f"- Bag tag scanned but flight/PNR not readable "
                f"(confidence: {state.ocr_confidence:.0%})"
            )
        if state.routing_lane == 1 and state.voucher_code:
            parts.append(f"- Claim decision: APPROVED (Lane 1)")
            parts.append(f"- Voucher code: {state.voucher_code}")
            parts.append(
                f"- Final compensation: ${state.final_compensation_usd:.2f} USD"
            )
        elif state.routing_lane == 2:
            parts.append(
                f"- Claim decision: UNDER REVIEW (Lane 2 — exceeds auto-approval threshold)"
            )

        if not parts:
            return ""

        return (
            "[ANALYSIS RESULTS — use these facts in your reply, do not ask the passenger for information already captured here]:\n"
            + "\n".join(parts)
        )

    def _get_step_prompt(self, state: ClaimState, prompts: dict) -> str:
        """
        Determine the correct prompt template for the current conversation step.

        Priority:
        1. conversation_ended — terminal state, no claim filed
        2. re_request_tag / re_request_damage — retry prompts
        3. result step — routing_lane set by A4
        4. Image received — damage images present regardless of conversation step.
           Handles frustrated passengers who upload photos without greeting first.
        5. Normal step prompt for text-only turns
        """
        steps = prompts.get("steps", {})

        # Terminal state — A4 found no damage OR passenger said no damage
        if state.conversation_ended:
            return steps.get("no_damage_terminal", "")

        if state.re_request_tag:
            return steps.get("re_request_tag", "")

        if state.re_request_damage:
            return steps.get("re_request_damage", "")

        if state.conversation_step == "result":
            if state.routing_lane == 1:
                return PromptLoader.render(
                    steps.get("result_lane1", ""),
                    {
                        "voucher_code": state.voucher_code or "N/A",
                        "compensation": f"{state.final_compensation_usd:.2f}",
                    },
                )
            elif state.routing_lane == 2:
                return PromptLoader.render(
                    steps.get("result_lane2", ""),
                    {"claim_id": state.claim_id or "N/A"},
                )
            else:
                logger.warning(
                    "a1_result_step_no_lane", extra={"session_id": state.session_id}
                )
                return steps.get("tag_photo_received", "")

        has_damage_images = any("tag" not in p.lower() for p in state.image_paths)
        has_tag_images = any("tag" in p.lower() for p in state.image_paths)

        # Check image presence BEFORE checking conversation_step — a passenger may
        # upload photos at ANY step including "greeting" (skipping text entirely).
        if has_tag_images and state.conversation_step in (
            "tag_photo",
            "confirm",
            "damage_photos",
        ):
            return steps.get("tag_photo_received", steps.get("confirm", ""))

        if has_damage_images:
            # Covers normal damage_photos step AND greeting step (user uploaded immediately).
            return steps.get("damage_photos_received", steps.get("tag_photo", ""))

        # Text-only turn — use normal step prompt
        return steps.get(state.conversation_step, steps.get("greeting", ""))

    def _build_messages(
        self, state: ClaimState, step_prompt: str, system_prompt: str
    ) -> List[dict]:
        messages = [{"role": "system", "content": system_prompt}]

        if state.conversation_history:
            messages.extend(state.conversation_history[-6:])

        if state.passenger_message:
            messages.append({"role": "user", "content": state.passenger_message})

        analysis_context = self._build_analysis_context(state)
        if analysis_context:
            messages.append({"role": "user", "content": analysis_context})

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
        Advance conversation_step to the next stage.

        Returns current step unchanged for any terminal condition:
        - conversation_ended (no damage, conversation closed)
        - re_request flags
        - already at result
        - routing_lane set (jumps to result)
        """
        # Terminal — no claim filed, conversation is over
        if state.conversation_ended:
            return "result"

        if state.re_request_tag or state.re_request_damage:
            return state.conversation_step

        if state.conversation_step == "result":
            return "result"

        if state.routing_lane is not None:
            return "result"

        # If user uploaded damage photos while still at greeting step,
        # advance to damage_photos so the step machine stays in sync.
        has_damage_images = any("tag" not in p.lower() for p in state.image_paths)
        if state.conversation_step == "greeting" and has_damage_images:
            return "damage_photos"

        current_index = (
            STEPS.index(state.conversation_step)
            if state.conversation_step in STEPS
            else 0
        )
        return STEPS[min(current_index + 1, len(STEPS) - 1)]

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        logger.info(
            "a1_started",
            extra={
                "component": "A1",
                "step": state.conversation_step,
                "session_id": state.session_id,
                "re_request_tag": state.re_request_tag,
                "re_request_damage": state.re_request_damage,
                "image_count": len(state.image_paths),
                "has_damage_analysis": bool(state.damage_types),
                "has_ocr_data": bool(state.flight_number or state.pnr),
                "conversation_ended": state.conversation_ended,
            },
        )

        try:
            prompts = PromptLoader.load("a1_conversation")
            system_prompt = prompts.get(
                "system", "You are a helpful airline assistant."
            )
            step_prompt = self._get_step_prompt(state, prompts)
            messages = self._build_messages(state, step_prompt, system_prompt)

            reply = await self._llm.chat(messages, temperature=0.3)

            # ── Detect no-damage terminal intent ──────────────────────────────
            # The system prompt instructs A1 to handle "no damage" gracefully.
            # We detect this by asking A1 to include [NO_CLAIM] in its reply
            # when it has determined no claim will be filed. We then strip the
            # marker and set conversation_ended so the frontend locks the input.
            # This is more reliable than parsing natural language for intent.
            if "[NO_CLAIM]" in reply:
                reply = reply.replace("[NO_CLAIM]", "").strip()
                state.conversation_ended = True
                logger.info(
                    "a1_no_claim_detected", extra={"session_id": state.session_id}
                )

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
                    "conversation_ended": state.conversation_ended,
                },
            )

        except Exception as exc:
            logger.exception("a1_failed")
            state.set_error(f"A1 error: {exc}")

        return state
