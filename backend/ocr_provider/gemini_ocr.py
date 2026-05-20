from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from PIL import Image

from backend.ocr_provider.base import OCRProvider, TagData

logger = logging.getLogger(__name__)

# ── Validation patterns ────────────────────────────────────────────────────────
# PNR: exactly 6 uppercase alphanumeric characters (IATA standard)
PNR_PATTERN = re.compile(r"^[A-Z0-9]{6}$")

# Bag ID: 10–12 digits (IATA standard is 10, but some tags print 12 with spaces stripped)
# Real-world tags like "0452 30 674234" → stripped → "045230674234" (12 digits)
BAG_ID_PATTERN = re.compile(r"^\d{10,12}$")

BAG_TAG_EXTRACTION_PROMPT = """You are an airline baggage handling system.
Analyze this airline bag tag image carefully.

Return ONLY a valid JSON object with exactly these fields:
{
  "flight_number": "AI202",
  "pnr": "ABC123",
  "bag_id": "045230674234",
  "confidence": 0.95
}

Rules:
- flight_number: string with the flight number including airline code (e.g. "AI202", "EK567", "TK1234").
  null if not present or not readable. Note: airport codes (e.g. "SAW", "BOM") are NOT flight numbers.
- pnr: string with exactly 6 uppercase alphanumeric characters (e.g. "ABC123").
  null if not present or not readable. PNR is not always printed on bag tags.
- bag_id: the baggage tag number as a CONTINUOUS STRING OF DIGITS ONLY.
  Remove ALL spaces — e.g. "0452 30 674234" becomes "045230674234".
  Typically 10–12 digits. null if not readable.
- confidence: float 0.0–1.0 representing how clearly readable the tag is
  1.0 = perfectly clear, all fields readable
  0.7 = mostly readable, minor blur
  0.5 = partially readable, some fields uncertain
  0.3 = very blurry or partially visible
  0.0 = unreadable / not a bag tag at all

Return ONLY the JSON object. No explanation, no markdown, no code blocks."""


class GeminiOCRProvider(OCRProvider):
    """
    Gemini Flash OCR implementation for airline bag tag data extraction.

    Uses the same Gemini 2.5 Flash multimodal model as GeminiVisionProvider —
    no extra API key or quota needed beyond T-006.
    POC uses free tier: 1500 requests/day, 1M tokens/day.
    Ref: https://ai.google.dev/pricing

    Future swap: set OCR_PROVIDER=paddleocr → paddleocr.py runs fully offline
    with no PII sent to any external API. Zero other changes needed.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        """
        Initialise the Gemini OCR provider.

        Args:
            api_key: Gemini API key from GEMINI_API_KEY env var.
            model:   Gemini model name. Defaults to gemini-2.5-flash.
        """
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._model_name = model

    def _load_image(self, image_path: str) -> Image.Image:
        """
        Load a bag tag image from disk for Gemini multimodal input.

        Args:
            image_path: Absolute or relative path to the image file.

        Returns:
            PIL Image object ready for Gemini API.

        Raises:
            FileNotFoundError: If the image path does not exist.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Bag tag image not found: {image_path}")
        return Image.open(path)

    def _parse_json_response(self, raw_text: str) -> dict:
        """
        Safely parse a JSON response from Gemini.

        Gemini sometimes wraps JSON in markdown code blocks — strips them first.

        Args:
            raw_text: Raw text response from Gemini.

        Returns:
            Parsed dict from the JSON response.

        Raises:
            ValueError: If the response cannot be parsed as valid JSON.
        """
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error(
                "gemini_ocr_json_parse_failed",
                extra={"raw": raw_text[:200], "error": str(exc)},
            )
            raise ValueError(
                f"Gemini OCR returned invalid JSON: {raw_text[:100]}"
            ) from exc

    def _validate_pnr(self, pnr: Optional[str]) -> Optional[str]:
        """
        Validate PNR format: exactly 6 uppercase alphanumeric characters.

        Args:
            pnr: Raw PNR string from Gemini response.

        Returns:
            Uppercased PNR if valid, None otherwise.
        """
        if not pnr:
            return None
        cleaned = str(pnr).strip().upper()
        if PNR_PATTERN.match(cleaned):
            return cleaned
        logger.warning(
            "gemini_ocr_invalid_pnr",
            extra={"pnr": pnr, "expected_pattern": r"[A-Z0-9]{6}"},
        )
        return None

    def _validate_bag_id(self, bag_id: Optional[str]) -> Optional[str]:
        """
        Validate bag ID format: 10–12 continuous digits.

        Strips spaces before validation — real airline tags often print
        the number with spaces (e.g. "0452 30 674234") but the underlying
        IATA number is a continuous digit string.

        Args:
            bag_id: Raw bag ID string from Gemini response.

        Returns:
            Space-stripped digit string if valid (10–12 digits), None otherwise.
        """
        if not bag_id:
            return None
        # Strip spaces — handles "0452 30 674234" → "045230674234"
        cleaned = str(bag_id).strip().replace(" ", "")
        if BAG_ID_PATTERN.match(cleaned):
            return cleaned
        logger.warning(
            "gemini_ocr_invalid_bag_id",
            extra={"bag_id": bag_id, "expected_pattern": r"\d{10,12}"},
        )
        return None

    async def extract_bag_tag(self, image_path: str) -> TagData:
        """
        Extract flight number, PNR, and bag ID from a bag tag photo.

        Sends the image to Gemini with a structured extraction prompt,
        parses the JSON response, and validates all field formats with regex.
        Low confidence (< 0.7) signals A3 to set re_request_tag = True,
        prompting the passenger to retake the photo.

        Args:
            image_path: Path to the bag tag photo (JPG/PNG/WEBP).

        Returns:
            TagData with flight_number, pnr, bag_id, and confidence (0.0–1.0).
            Any field that fails format validation is returned as None.
            Returns TagData(confidence=0.0) on any unexpected error.

        Raises:
            FileNotFoundError: If image_path does not exist on disk.
        """
        logger.info(
            "gemini_ocr_extract_tag_started",
            extra={"image": image_path, "model": self._model_name},
        )

        try:
            image = self._load_image(image_path)
            response = self._model.generate_content([BAG_TAG_EXTRACTION_PROMPT, image])
            parsed = self._parse_json_response(response.text)

            # Normalise and validate each field
            raw_flight = parsed.get("flight_number")
            flight_number = raw_flight.strip().upper() if raw_flight else None
            pnr = self._validate_pnr(parsed.get("pnr"))
            bag_id = self._validate_bag_id(parsed.get("bag_id"))
            confidence = float(parsed.get("confidence", 0.0))

            result = TagData(
                flight_number=flight_number,
                pnr=pnr,
                bag_id=bag_id,
                confidence=confidence,
            )

            logger.info(
                "gemini_ocr_extract_tag_completed",
                extra={
                    "image": image_path,
                    "flight_number": result.flight_number,
                    "pnr": result.pnr,
                    "bag_id": result.bag_id,
                    "confidence": result.confidence,
                },
            )
            return result

        except FileNotFoundError:
            raise  # let caller handle missing files — don't silently swallow

        except Exception as exc:
            logger.exception(
                "gemini_ocr_extract_tag_failed",
                extra={"image": image_path, "error": str(exc)},
            )
            return TagData(confidence=0.0)