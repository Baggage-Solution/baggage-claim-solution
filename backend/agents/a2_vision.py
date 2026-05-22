from __future__ import annotations

import logging
from typing import List

from backend.agents.base_agent import BaseAgent
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

# Compensation scale: severity 0.0 (no damage) → $0, severity 1.0 (destroyed) → $150.
# A4 applies 1.5× luxury multiplier on top of this estimate.
# Threshold: LANE1_MAX_COMPENSATION_USD=100 — above this A4 routes to Lane 2.
_SEVERITY_TO_USD_SCALE = 150.0

# Minimum vision confidence for damage photos to be accepted.
# Below this threshold the passenger is asked to retake the photos.
_MIN_ACCEPTABLE_CONFIDENCE = 0.4


class A2VisionAgent(BaseAgent):
    """
    Agent A2 — Vision Analysis.

    Responsibilities:
    - Analyse damage photos: identify damage types, severity, brand.
    - Set is_luxury flag for luxury brand bags.
    - Produce initial compensation_estimate_usd.
    - Set re_request_damage if image quality is too low.

    Provider: VisionProvider (injected — never import Gemini directly here).
    Future swap: set VISION_PROVIDER=yolov8 in .env → yolov8_vision.py used instead.
    """

    def __init__(self, vision) -> None:
        super().__init__(name="a2_vision", description="Damage vision analysis agent")
        self._vision = vision  # VisionProvider instance

    def _is_damage_photo(self, image_path: str) -> bool:
        """
        Return True if this image is a damage photo (not a bag tag photo).

        A3 handles paths containing 'tag' in the filename.
        A2 processes everything else.

        Args:
            image_path: Path string to check.

        Returns:
            True if this is a damage photo, False if it is a tag photo.
        """
        return "tag" not in image_path.lower()

    def _calculate_compensation(self, severity_score: float) -> float:
        """
        Calculate initial compensation estimate from severity score.

        Linear scale: severity 0.0 → $0.00, severity 1.0 → $150.00.
        A4 applies 1.5× luxury multiplier on top of this.
        LANE1_MAX_COMPENSATION_USD=100 determines Lane 1 / Lane 2 cutoff.

        Args:
            severity_score: Float 0.0–1.0 from VisionProvider.analyze_damage().

        Returns:
            Compensation estimate in USD, rounded to 2 decimal places.
        """
        return round(severity_score * _SEVERITY_TO_USD_SCALE, 2)

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        """
        Run vision analysis on all damage photos in state.image_paths.

        Steps:
        1. Filter image_paths to damage photos (paths without 'tag' in name).
        2. For each damage photo: analyze_damage() → aggregate damage_types + severity.
        3. classify_brand() on first damage photo → brand_detected, is_luxury.
        4. If confidence too low across all photos → re_request_damage = True.
        5. Calculate compensation_estimate_usd from max severity_score.

        Args:
            state: Current ClaimState with image_paths from /upload endpoint.
            tasks: Reserved for future task injection — unused in A2.

        Returns:
            Updated ClaimState with A2 outputs populated.
        """
        logger.info(
            "a2_started",
            extra={"component": "A2", "image_count": len(state.image_paths)},
        )

        try:
            # ── Short-circuit: no images uploaded yet ──────────────────────────
            if not state.image_paths:
                logger.info("a2_skipped", extra={"reason": "no_images"})
                return state

            # ── Step 1: Filter — damage photos only ───────────────────────────
            damage_photos = [p for p in state.image_paths if self._is_damage_photo(p)]

            if not damage_photos:
                logger.info(
                    "a2_skipped",
                    extra={"reason": "no_damage_photos_only_tag"},
                )
                return state

            # ── Step 2: Analyse each damage photo ─────────────────────────────
            all_damage_types: List[str] = []
            max_severity: float = 0.0
            max_confidence: float = 0.0

            for image_path in damage_photos:
                result = await self._vision.analyze_damage(image_path)
                all_damage_types.extend(result.damage_types)
                max_severity = max(max_severity, result.severity_score)
                max_confidence = max(max_confidence, result.confidence)

                logger.info(
                    "a2_damage_analyzed",
                    extra={
                        "image": image_path,
                        "damage_types": result.damage_types,
                        "severity": result.severity_score,
                        "confidence": result.confidence,
                    },
                )

            # ── Step 3: Re-request if all images too blurry ───────────────────
            if max_confidence < _MIN_ACCEPTABLE_CONFIDENCE:
                logger.warning(
                    "a2_low_confidence",
                    extra={
                        "max_confidence": max_confidence,
                        "threshold": _MIN_ACCEPTABLE_CONFIDENCE,
                    },
                )
                state.re_request_damage = True
                return state

            # ── Step 4: Brand classification (use first damage photo) ──────────
            brand_result = await self._vision.classify_brand(damage_photos[0])

            # ── Step 5: Write all A2 outputs into ClaimState ───────────────────
            # Deduplicate damage types — same type may appear across multiple photos
            state.damage_types = list(dict.fromkeys(all_damage_types))
            state.severity_score = round(max_severity, 4)
            state.brand_detected = brand_result.brand
            state.is_luxury = brand_result.is_luxury
            state.compensation_estimate_usd = self._calculate_compensation(max_severity)

            state.add_debug("a2_images_processed", len(damage_photos))
            state.add_debug("a2_brand_confidence", brand_result.confidence)

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
            },
        )
        return state
