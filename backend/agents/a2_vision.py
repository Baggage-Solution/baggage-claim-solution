from __future__ import annotations

import logging
from typing import List

from backend.agents.base_agent import BaseAgent
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

_SEVERITY_TO_USD_SCALE = 150.0
_MIN_ACCEPTABLE_CONFIDENCE = 0.4
_NO_DAMAGE_SEVERITY = 0.1

# Object gate: below this bag-confidence we treat the image as "not a bag".
# Gemini returns is_bag plus a confidence; we require BOTH a positive is_bag
# AND reasonable confidence so a hesitant "maybe a bag" doesn't slip through.
_MIN_BAG_CONFIDENCE = 0.5

# Tag-in-damage-photo: only hand a damage image to A3 for OCR when the tag in it
# looks legible enough to be worth a call. Per product decision: high confidence
# only; otherwise fall back to asking for a dedicated tag photo.
_MIN_EMBEDDED_TAG_CONFIDENCE = 0.7

# After this many consecutive non-bag uploads, A1 gently ends the conversation.
NON_BAG_ATTEMPT_LIMIT = 3


class A2VisionAgent(BaseAgent):
    """
    Agent A2 — Vision Analysis.

    Per uploaded image, in ONE Gemini call (analyze_image), A2 determines:
      • is this luggage at all?   → object gate (issue #1)
      • damage type + severity
      • brand / luxury
      • is a legible bag tag visible in the frame? → lets A3 OCR the same image
        instead of requiring a separate tag upload (issues #2 and #4)
    """

    def __init__(self, vision) -> None:
        super().__init__(name="a2_vision", description="Damage vision analysis agent")
        self._vision = vision

    def _is_damage_photo(self, image_path: str) -> bool:
        return "tag" not in image_path.lower()

    def _calculate_compensation(self, severity_score: float) -> float:
        return round(severity_score * _SEVERITY_TO_USD_SCALE, 2)

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        """Run vision analysis on all new damage photos in state.image_paths.

        Calls VisionProvider.analyze_image() for each unprocessed damage photo,
        runs the object gate (issue #1), detects embedded tags (issues #2/#4),
        and writes damage_types, severity_score, brand_detected, and is_luxury
        to state.

        Args:
            state: The shared ClaimState from the LangGraph pipeline.
            tasks: Unused — present for BaseAgent interface compliance.

        Returns:
            ClaimState: Updated state with vision analysis results.
        """
        logger.info(
            "a2_started",
            extra={"component": "A2", "image_count": len(state.image_paths)},
        )

        try:
            if not state.image_paths:
                logger.info("a2_skipped", extra={"reason": "no_images"})
                return state

            all_damage_photos = [
                p for p in state.image_paths if self._is_damage_photo(p)
            ]
            if not all_damage_photos:
                logger.info("a2_skipped", extra={"reason": "no_damage_photos_only_tag"})
                return state

            already_processed = set(state.processed_damage_paths)
            damage_photos = [p for p in all_damage_photos if p not in already_processed]
            if not damage_photos:
                logger.info(
                    "a2_skipped",
                    extra={
                        "reason": "all_damage_photos_already_processed",
                        "count": len(all_damage_photos),
                    },
                )
                return state

            # Clear per-turn flags before re-evaluating this turn's new photos.
            state.no_damage_detected = False
            state.re_request_damage = False
            state.not_a_bag = False
            state.tag_in_damage_photo = False

            # ── Analyse each NEW image with the combined single-call method ───
            scenes = []
            for image_path in damage_photos:
                scene = await self._vision.analyze_image(image_path)
                scenes.append((image_path, scene))
                logger.info(
                    "a2_image_analyzed",
                    extra={
                        "image": image_path,
                        "is_bag": scene.is_bag,
                        "bag_confidence": scene.bag_confidence,
                        "object": scene.object_description,
                        "damage_types": scene.damage_types,
                        "severity": scene.severity_score,
                        "tag_visible": scene.tag_visible,
                        "tag_confidence": scene.tag_confidence,
                    },
                )

            # These images have now cost a Gemini call — never re-analyse them.
            state.processed_damage_paths = list(already_processed) + damage_photos

            # ── ISSUE #1: object gate ─────────────────────────────────────────
            # An image counts as a bag if the model is confident it is luggage.
            bag_scenes = [
                (p, s)
                for (p, s) in scenes
                if s.is_bag and s.bag_confidence >= _MIN_BAG_CONFIDENCE
            ]

            if not bag_scenes:
                # None of the new images is a bag. Do not pretend we analysed one.
                state.non_bag_attempts += 1
                state.not_a_bag = True
                # Roll back: these junk images should not block a later real bag,
                # and should not count as "damage photos" for routing.
                state.processed_damage_paths = [
                    p for p in state.processed_damage_paths if p not in damage_photos
                ]
                # Surface the best description for A1's reply.
                state.last_object_description = next(
                    (s.object_description for (_, s) in scenes if s.object_description),
                    None,
                )
                logger.info(
                    "a2_not_a_bag",
                    extra={
                        "attempts": state.non_bag_attempts,
                        "object": state.last_object_description,
                        "limit": NON_BAG_ATTEMPT_LIMIT,
                    },
                )
                return state

            # We have at least one real bag — reset the non-bag counter.
            state.non_bag_attempts = 0
            state.last_object_description = None

            # ── ISSUE #2 / #4: tags embedded in the damage photo(s) ───────────
            # If any bag photo also shows a legible tag, mark it for A3 to OCR.
            tag_candidates = [
                p
                for (p, s) in bag_scenes
                if s.tag_visible and s.tag_confidence >= _MIN_EMBEDDED_TAG_CONFIDENCE
            ]
            if tag_candidates:
                state.tag_in_damage_photo = True
                # Merge with any prior candidates, de-duped, excluding ones A3 already did.
                existing = set(state.tag_candidate_paths)
                done = set(state.processed_tag_paths)
                state.tag_candidate_paths = [
                    p for p in (list(existing) + tag_candidates) if p not in done
                ]
                logger.info(
                    "a2_tag_in_damage_photo",
                    extra={"candidates": state.tag_candidate_paths},
                )

            # ── Aggregate damage / brand across the bag photos ────────────────
            all_damage_types: List[str] = list(state.damage_types)
            max_severity: float = state.severity_score
            max_damage_conf: float = 0.0
            best_brand = None
            best_is_luxury = state.is_luxury
            best_brand_conf = -1.0

            for _, s in bag_scenes:
                all_damage_types.extend(s.damage_types)
                max_severity = max(max_severity, s.severity_score)
                max_damage_conf = max(max_damage_conf, s.damage_confidence)
                if s.brand_confidence > best_brand_conf:
                    best_brand_conf = s.brand_confidence
                    best_brand = s.brand
                    best_is_luxury = s.is_luxury

            deduped_types = list(dict.fromkeys(all_damage_types))

            # ── Re-request if the bag image was too blurry to judge ───────────
            if max_damage_conf < _MIN_ACCEPTABLE_CONFIDENCE:
                logger.warning(
                    "a2_low_confidence",
                    extra={
                        "max_confidence": max_damage_conf,
                        "threshold": _MIN_ACCEPTABLE_CONFIDENCE,
                    },
                )
                state.re_request_damage = True
                return state

            # ── No structural damage on a clear bag photo ─────────────────────
            no_real_damage = (not deduped_types) and (
                max_severity <= _NO_DAMAGE_SEVERITY
            )
            if no_real_damage:
                logger.info(
                    "a2_no_damage_detected",
                    extra={
                        "max_severity": max_severity,
                        "max_confidence": max_damage_conf,
                    },
                )
                state.damage_types = []
                state.severity_score = round(max_severity, 4)
                state.compensation_estimate_usd = 0.0
                state.no_damage_detected = True
                # Brand still recorded — it came for free in the same call.
                state.brand_detected = best_brand
                state.is_luxury = best_is_luxury
                state.add_debug("a2_images_processed", len(damage_photos))
                state.add_debug("a2_no_damage", True)
                logger.info(
                    "a2_completed",
                    extra={
                        "component": "A2",
                        "severity": state.severity_score,
                        "no_damage_detected": True,
                        "compensation_usd": state.compensation_estimate_usd,
                    },
                )
                return state

            # ── Real damage found ─────────────────────────────────────────────
            state.damage_types = deduped_types
            state.severity_score = round(max_severity, 4)
            state.brand_detected = best_brand
            state.is_luxury = best_is_luxury
            state.compensation_estimate_usd = self._calculate_compensation(max_severity)
            state.no_damage_detected = False

            state.add_debug("a2_images_processed", len(damage_photos))
            state.add_debug("a2_brand_confidence", best_brand_conf)

        except Exception as exc:
            logger.exception("a2_failed")
            state.set_error(f"A2 error: {exc}")

        logger.info(
            "a2_completed",
            extra={
                "component": "A2",
                "severity": state.severity_score,
                "is_luxury": state.is_luxury,
                "compensation_usd": state.compensation_estimate_usd,
                "no_damage_detected": state.no_damage_detected,
                "not_a_bag": state.not_a_bag,
                "tag_in_damage_photo": state.tag_in_damage_photo,
            },
        )
        return state
