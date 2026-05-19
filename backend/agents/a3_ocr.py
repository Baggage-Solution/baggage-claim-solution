from __future__ import annotations

import logging
import re
from typing import List

from backend.agents.base_agent import BaseAgent
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

# Validation patterns from architecture doc
PNR_PATTERN = re.compile(r"^[A-Z0-9]{6}$")
BAG_ID_PATTERN = re.compile(r"^\d{10}$")
OCR_CONFIDENCE_THRESHOLD = 0.7


class A3OCRAgent(BaseAgent):
    """
    Agent A3 — OCR / Data Extraction.

    Responsibilities:
    - Extract flight_number, pnr, bag_id from bag tag photo.
    - Validate formats with regex.
    - Set state.ocr_confidence; if < 0.7 set re_request_tag = True.

    Provider: OCRProvider (injected — never import Gemini directly here).
    Future swap: set OCR_PROVIDER=paddleocr in .env → paddleocr.py is used instead.
    """

    def __init__(self, ocr) -> None:
        super().__init__(name="a3_ocr", description="Bag tag OCR extraction agent")
        self._ocr = ocr  # OCRProvider instance

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        logger.info("a3_started", extra={"component": "A3"})

        try:
            tag_images = [p for p in state.image_paths if "tag" in p.lower()]
            if not tag_images:
                logger.info("a3_skipped", extra={"reason": "no_tag_images"})
                return state

            # TODO (T-011): implement OCR extraction
            # Steps:
            # 1. self._ocr.extract_bag_tag(tag_images[0]) → TagData
            # 2. Validate PNR with PNR_PATTERN, bag_id with BAG_ID_PATTERN
            # 3. Set state.pnr, flight_number, bag_id, ocr_confidence
            # 4. If ocr_confidence < OCR_CONFIDENCE_THRESHOLD:
            #      state.re_request_tag = True (A1 will ask passenger to retake)
            # 5. Log low-confidence cases for monitoring

            state.pnr = "ABC123"  # stub
            state.flight_number = "AI202"
            state.bag_id = "1234567890"
            state.ocr_confidence = 0.92
            state.add_debug("a3_confidence", state.ocr_confidence)

            if state.ocr_confidence < OCR_CONFIDENCE_THRESHOLD:
                state.re_request_tag = True
                logger.info(
                    "a3_low_confidence", extra={"confidence": state.ocr_confidence}
                )

        except Exception as exc:
            logger.exception("a3_failed")
            state.set_error(f"A3 error: {exc}")

        logger.info("a3_completed", extra={"component": "A3", "pnr": state.pnr})
        return state
