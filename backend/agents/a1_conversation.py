from __future__ import annotations

import logging
from typing import List

from backend.agents.a2_vision import NON_BAG_ATTEMPT_LIMIT
from backend.agents.base_agent import BaseAgent
from backend.core.prompt_loader import PromptLoader
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

STEPS = ["greeting", "damage_photos", "tag_photo", "confirm", "result"]


class A1ConversationAgent(BaseAgent):
    """
    Agent A1 — Passenger Conversation.

    On image turns A1 runs AFTER A2 and A3, so state already carries the object
    gate (not_a_bag), damage, brand, tag presence, and any OCR/manual tag data.
    A1 turns all of that into one natural-language reply and never assumes facts
    the analysis did not establish.
    """

    def __init__(self, llm) -> None:
        super().__init__(
            name="a1_conversation", description="Passenger conversation agent"
        )
        self._llm = llm

    def _build_analysis_context(self, state: ClaimState) -> str:
        parts = []

        # Object gate first — if it's not a bag, that's the only fact that matters.
        if state.not_a_bag:
            obj = state.last_object_description or "something that is not a bag"
            parts.append(
                f"- Object check: the uploaded image does NOT appear to be a "
                f"piece of luggage. It looks like: {obj}."
            )
            parts.append(f"- Non-bag attempts so far: {state.non_bag_attempts}.")
            return (
                "[ANALYSIS RESULTS — use these facts, do not invent a bag]:\n"
                + "\n".join(parts)
            )

        # Damage verdict.
        if state.no_damage_detected:
            parts.append(
                "- Damage assessment: NO visible structural damage detected. "
                "The bag appears intact (only cosmetic marks, if any)."
            )
        elif state.damage_types:
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

        if not state.no_damage_detected:
            if state.brand_detected:
                luxury_note = (
                    " (luxury brand — 1.5× compensation applies)"
                    if state.is_luxury
                    else ""
                )
                parts.append(f"- Bag brand: {state.brand_detected}{luxury_note}")
            if state.compensation_estimate_usd > 0:
                parts.append(
                    f"- Estimated compensation: ${state.compensation_estimate_usd:.2f} USD"
                )

            # Tag data — note its source (OCR vs manual vs found-in-photo).
            if state.tag_in_damage_photo and not state.tag_manually_entered:
                parts.append(
                    "- A bag tag was also visible in the damage photo and was read "
                    "automatically."
                )
            if state.tag_manually_entered:
                parts.append("- Tag details were provided manually by the passenger.")
            if state.flight_number:
                parts.append(f"- Flight number from tag: {state.flight_number}")
            if state.pnr:
                parts.append(f"- PNR from tag: {state.pnr}")
            if state.bag_id:
                parts.append(f"- Bag ID from tag: {state.bag_id}")
            if (
                state.ocr_confidence > 0
                and not state.flight_number
                and not state.pnr
                and not state.bag_id
            ):
                parts.append(
                    f"- Bag tag scanned but no fields readable "
                    f"(confidence: {state.ocr_confidence:.0%})"
                )

        if state.routing_lane == 1 and state.voucher_code:
            parts.append("- Claim decision: APPROVED (Lane 1)")
            parts.append(f"- Voucher code: {state.voucher_code}")
            parts.append(
                f"- Final compensation: ${state.final_compensation_usd:.2f} USD"
            )
        elif state.routing_lane == 2:
            parts.append(
                "- Claim decision: UNDER REVIEW (Lane 2 — exceeds auto-approval threshold)"
            )

        if not parts:
            return ""

        return (
            "[ANALYSIS RESULTS — use these facts in your reply, do not ask the "
            "passenger for information already captured here]:\n" + "\n".join(parts)
        )

    def _get_step_prompt(self, state: ClaimState, prompts: dict) -> str:
        steps = prompts.get("steps", {})

        # 1. Terminal — passenger confirmed no damage, or non-bag limit reached.
        if state.conversation_ended:
            return steps.get("no_damage_terminal", "")

        # 2. ISSUE #1 — not a bag.
        if state.not_a_bag:
            if state.non_bag_attempts >= NON_BAG_ATTEMPT_LIMIT:
                return steps.get("not_a_bag_terminal", steps.get("not_a_bag", ""))
            return steps.get("not_a_bag", "")

        # 3. No-damage on a clear bag photo.
        if state.no_damage_detected:
            return steps.get("no_damage_found", "")

        # 4. Blurry retries — but if we can offer manual entry, prefer that prompt.
        if state.re_request_tag:
            if state.offer_manual_entry:
                return steps.get("tag_unreadable_offer_manual", steps.get("re_request_tag", ""))
            return steps.get("re_request_tag", "")
        if state.re_request_damage:
            return steps.get("re_request_damage", "")

        # 5. Final result after A4 routing.
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

        # When the passenger is replying at the confirm step (e.g. typing "yes"),
        # use the confirm prompt — do NOT fall through to an image-received prompt
        # that would wrongly re-ask for a tag.
        if state.conversation_step == "confirm":
            return steps.get("confirm", steps.get("tag_photo_received", ""))

        # 6. ISSUE #2 / #4 — damage photo(s) + usable tag data captured in the
        #    same flow (tag inside the photo, both uploaded together, or manual).
        #    Summarise everything and ask the passenger to confirm or correct.
        if (
            state.conversation_step not in ("confirm", "result")
            and has_damage_images
            and state.damage_types
            and state.tag_data_complete
        ):
            return steps.get("combined_photo_received", steps.get("tag_photo_received", ""))

        # 7. Dedicated tag photo received.
        if has_tag_images and state.conversation_step in (
            "tag_photo",
            "confirm",
            "damage_photos",
        ):
            return steps.get("tag_photo_received", steps.get("confirm", ""))

        # 8. Damage photo received (real damage, no tag yet) → ask for tag.
        if has_damage_images:
            return steps.get("damage_photos_received", steps.get("tag_photo", ""))

        # 9. Text-only turn.
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
        # Terminal.
        if state.conversation_ended:
            return "result"

        # Not a bag — never advance; stay where we are (or sit at damage_photos
        # if the passenger jumped straight in at greeting).
        if state.not_a_bag:
            return (
                "damage_photos"
                if state.conversation_step == "greeting"
                else state.conversation_step
            )

        # No damage — hold on the photo step.
        if state.no_damage_detected:
            return (
                "damage_photos"
                if state.conversation_step == "greeting"
                else state.conversation_step
            )

        if state.re_request_tag or state.re_request_damage:
            return state.conversation_step

        if state.conversation_step == "result":
            return "result"
        if state.routing_lane is not None:
            return "result"

        # ISSUE #2 / #4 — damage + complete tag in one shot: jump straight to
        # confirm (skip the separate tag_photo step). Only when we have NOT yet
        # reached confirm — otherwise a plain "yes" at the confirm step would
        # re-trigger this branch and never advance to "result".
        has_damage_images = any("tag" not in p.lower() for p in state.image_paths)
        if (
            state.conversation_step not in ("confirm", "result")
            and has_damage_images
            and state.damage_types
            and state.tag_data_complete
        ):
            return "confirm"

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
                "not_a_bag": state.not_a_bag,
                "non_bag_attempts": state.non_bag_attempts,
                "re_request_tag": state.re_request_tag,
                "re_request_damage": state.re_request_damage,
                "no_damage_detected": state.no_damage_detected,
                "tag_in_damage_photo": state.tag_in_damage_photo,
                "tag_data_complete": state.tag_data_complete,
                "offer_manual_entry": state.offer_manual_entry,
                "image_count": len(state.image_paths),
                "conversation_ended": state.conversation_ended,
            },
        )

        try:
            prompts = PromptLoader.load("a1_conversation")
            system_prompt = prompts.get(
                "system", "You are a helpful airline assistant."
            )

            # Non-bag attempt limit reached → end the conversation gently.
            if state.not_a_bag and state.non_bag_attempts >= NON_BAG_ATTEMPT_LIMIT:
                state.conversation_ended = True

            step_prompt = self._get_step_prompt(state, prompts)
            messages = self._build_messages(state, step_prompt, system_prompt)

            reply = await self._llm.chat(messages, temperature=0.3)

            if "[NO_CLAIM]" in reply:
                reply = reply.replace("[NO_CLAIM]", "").strip()
                state.conversation_ended = True
                state.no_damage_detected = False
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
                    "not_a_bag": state.not_a_bag,
                },
            )

        except Exception as exc:
            logger.exception("a1_failed")
            state.set_error(f"A1 error: {exc}")

        return state