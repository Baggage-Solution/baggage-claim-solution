from __future__ import annotations

import logging
from typing import List

from backend.agents.base_agent import BaseAgent
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)


class A2VisionAgent(BaseAgent):
    """
    Agent A2 — Vision Analysis.

    Responsibilities:
    - Analyse damage photos: identify damage types, severity, brand.
    - Set is_luxury flag for luxury brand bags.
    - Produce initial compensation_estimate_usd.
    - Set re_request_damage if image quality is too low.

    Provider: VisionProvider (injected — never import Gemini directly here).
    Future swap: set VISION_PROVIDER=yolov8 in .env → yolov8_vision.py is used instead.
    """

    def __init__(self, vision) -> None:
        super().__init__(name="a2_vision", description="Damage vision analysis agent")
        self._vision = vision  # VisionProvider instance

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        logger.info(
            "a2_started",
            extra={"component": "A2", "image_count": len(state.image_paths)},
        )

        try:
            if not state.image_paths:
                logger.info("a2_skipped", extra={"reason": "no_images"})
                return state

            # TODO (T-010): implement vision analysis
            # Steps:
            # 1. Filter image_paths to damage photos (exclude tag photo — handled by A3)
            # 2. For each damage image: self._vision.analyze_damage(image_path) → DamageResult
            # 3. Aggregate damage_types, severity_score across all images
            # 4. self._vision.classify_brand(image_path) → BrandResult
            # 5. Set state.damage_types, severity_score, brand_detected, is_luxury
            # 6. Calculate state.compensation_estimate_usd from severity_score
            # 7. If image quality too low: state.re_request_damage = True

            state.damage_types = ["[stub] cracked shell"]
            state.severity_score = 0.4
            state.compensation_estimate_usd = 40.0
            state.add_debug("a2_images_processed", len(state.image_paths))

        except Exception as exc:
            logger.exception("a2_failed")
            state.set_error(f"A2 error: {exc}")

        logger.info(
            "a2_completed", extra={"component": "A2", "severity": state.severity_score}
        )
        return state
