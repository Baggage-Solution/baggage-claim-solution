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
    - Skip re-extraction of tag photos already processed in a prior turn
      (prevents a redundant Gemini OCR call on the confirm turn).

    Provider: OCRProvider (injected — never import Gemini directly here).
    Future swap: set OCR_PROVIDER=paddleocr in .env → paddleocr.py used instead.
    """

    def __init__(self, ocr) -> None:
        super().__init__(name="a3_ocr", description="Bag tag OCR extraction agent")
        self._ocr = ocr  # OCRProvider instance

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        """
        Extract bag tag data from the tag photo in state.image_paths.

        The frontend resends ALL accumulated image paths every turn (so A4 has
        the full set for fraud checks). On the confirm turn the already-scanned
        tag image is resent alongside the damage images. Without a guard A3 would
        call Gemini OCR again on that same tag — a wasted call and extra latency.
        state.processed_tag_paths (echoed back by the frontend, mirroring A2's
        processed_damage_paths) lets A3 skip tags it has already read.

        Steps:
        1. Filter image_paths to tag photos (paths containing 'tag').
        2. Skip any tag already in state.processed_tag_paths (already scanned).
        3. Call self._ocr.extract_bag_tag() on the first NEW tag image.
        4. If confidence < OCR_CONFIDENCE_THRESHOLD → set re_request_tag = True.
        5. Write flight_number, pnr, bag_id, ocr_confidence to ClaimState.
        6. Record the scanned tag in processed_tag_paths.

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

            # ── Step 2: Skip tags already scanned in a prior turn ─────────────
            # On the confirm turn the tag image is resent. We already have its
            # data in state (echoed from the frontend), so re-running OCR is a
            # pure waste of a Gemini call. Skip and keep the existing values.
            already_processed = set(state.processed_tag_paths)
            new_tags = [p for p in tag_images if p not in already_processed]

            if not new_tags:
                logger.info(
                    "a3_skipped",
                    extra={
                        "reason": "all_tag_photos_already_processed",
                        "count": len(tag_images),
                    },
                )
                return state

            # Clear any stale retry flag before re-evaluating this turn's tag.
            state.re_request_tag = False

            # ── Step 3: Extract tag data from the first NEW tag image ─────────
            target_tag = new_tags[0]
            result = await self._ocr.extract_bag_tag(target_tag)

            # ── Step 4: Write confidence immediately ──────────────────────────
            state.ocr_confidence = result.confidence
            state.add_debug("a3_confidence", result.confidence)

            # ── Step 5: Re-request if confidence too low ──────────────────────
            # Note: a low-confidence tag is NOT marked processed, so the passenger
            # can retake it and A3 will run OCR again on the new photo.
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

            # ── Step 6: Write all fields to state ─────────────────────────────
            state.flight_number = result.flight_number
            state.pnr = result.pnr
            state.bag_id = result.bag_id

            # Mark this tag as scanned so the confirm turn doesn't re-OCR it.
            state.processed_tag_paths = list(already_processed) + [target_tag]

            # Log any fields the provider could not extract (for monitoring)
            if not state.pnr:
                logger.warning(
                    "a3_pnr_not_extracted",
                    extra={"image": target_tag},
                )
            if not state.bag_id:
                logger.warning(
                    "a3_bag_id_not_extracted",
                    extra={"image": target_tag},
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