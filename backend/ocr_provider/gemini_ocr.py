from __future__ import annotations

import logging

from backend.ocr_provider.base import OCRProvider, TagData

logger = logging.getLogger(__name__)


class GeminiOCRProvider(OCRProvider):
    """
    Gemini Flash OCR implementation (POC — same free API key as vision).
    Future swap: set OCR_PROVIDER=paddleocr → paddleocr.py (offline, no PII egress).
    """

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)

    async def extract_bag_tag(self, image_path: str) -> TagData:
        # TODO (T-007):
        # 1. Load image from image_path
        # 2. Prompt: "Read this airline bag tag. Extract and return JSON:
        #      flight_number (str), pnr (str, 6 chars), bag_id (str, 10 digits),
        #      confidence (0.0-1.0 how readable the tag is)"
        # 3. Parse JSON → TagData
        # 4. Validate formats: PNR=[A-Z0-9]{6}, bag_id=\d{10}
        # 5. Return TagData (low confidence → A3 will set re_request_tag=True)
        logger.info("gemini_ocr_extract_tag", extra={"image": image_path})
        return TagData(confidence=0.0)
