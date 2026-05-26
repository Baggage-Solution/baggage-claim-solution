from __future__ import annotations

import logging
import re
from typing import List

from backend.agents.base_agent import BaseAgent
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

# Validation patterns — T-007 fix: bag IDs can be 10–12 digits on real airline tags
PNR_PATTERN = re.compile(r"^[A-Z0-9]{6}$")
BAG_ID_PATTERN = re.compile(
    r"^\d{10,12}$"
)  # updated from \d{10} based on T-007 smoke test

# Minimum OCR confidence to accept tag data.
# Below this threshold the passenger is asked to retake the bag tag photo.
OCR_CONFIDENCE_THRESHOLD = 0.7


class A3OCRAgent(BaseAgent):
    """
    Agent A3 — OCR / Data Extraction.

    Responsibilities:
    - Extract flight_number, pnr, bag_id from the bag tag photo.
    - Write ocr_confidence to ClaimState for downstream monitoring.
    - Set re_request_tag = True if image quality is too low for reliable extraction.

    Provider: OCRProvider (injected — never import Gemini directly here).
    Future swap: set OCR_PROVIDER=paddleocr in .env → paddleocr.py used instead.
    """

    def __init__(self, ocr) -> None:
        super().__init__(name="a3_ocr", description="Bag tag OCR extraction agent")
        self._ocr = ocr  # OCRProvider instance

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        """
        Extract bag tag data from the tag photo in state.image_paths.

        Steps:
        1. Filter image_paths to tag photos (paths containing 'tag').
        2. Call self._ocr.extract_bag_tag() on the first tag image.
        3. If confidence < OCR_CONFIDENCE_THRESHOLD → set re_request_tag = True.
        4. Write flight_number, pnr, bag_id, ocr_confidence to ClaimState.
        5. Log warnings for any fields the provider could not extract.

        Args:
            state: Current ClaimState with image_paths from /upload endpoint.
            tasks: Reserved for future task injection — unused in A3.

        Returns:
            Updated ClaimState with A3 outputs populated.
        """
        logger.info("a3_started", extra={"component": "A3"})

        try:
            # ── Step 1: Filter — tag photos only ──────────────────────────────
            tag_images = [p for p in state.image_paths if "tag" in p.lower()]

            if not tag_images:
                logger.info("a3_skipped", extra={"reason": "no_tag_images"})
                return state

            # ── Step 2: Extract tag data from the first tag image ─────────────
            result = await self._ocr.extract_bag_tag(tag_images[0])

            # ── Step 3: Write confidence immediately ──────────────────────────
            state.ocr_confidence = result.confidence
            state.add_debug("a3_confidence", result.confidence)

            # ── Step 4: Re-request if confidence too low ──────────────────────
            if result.confidence < OCR_CONFIDENCE_THRESHOLD:
                logger.info(
                    "a3_low_confidence",
                    extra={
                        "confidence": result.confidence,
                        "threshold": OCR_CONFIDENCE_THRESHOLD,
                    },
                )
                state.re_request_tag = True
                return state

            # ── Step 5: Write all fields to state ─────────────────────────────
            state.flight_number = result.flight_number
            state.pnr = result.pnr
            state.bag_id = result.bag_id

            # Log any fields the provider could not extract (for monitoring)
            if not state.pnr:
                logger.warning(
                    "a3_pnr_not_extracted",
                    extra={"image": tag_images[0]},
                )
            if not state.bag_id:
                logger.warning(
                    "a3_bag_id_not_extracted",
                    extra={"image": tag_images[0]},
                )

        except Exception as exc:
            logger.exception("a3_failed")
            state.set_error(f"A3 error: {exc}")

        logger.info(
            "a3_completed",
            extra={
                "component": "A3",
                "pnr": state.pnr,
                "flight_number": state.flight_number,
                "bag_id": state.bag_id,
                "confidence": state.ocr_confidence,
            },
        )
        return state
