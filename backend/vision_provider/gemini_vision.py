from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from PIL import Image

from backend.vision_provider.base import (BrandResult, DamageResult,
                                          VisionProvider)

logger = logging.getLogger(__name__)

LUXURY_BRANDS = {
    "rimowa",
    "louis vuitton",
    "tumi",
    "brics",
    "zero halliburton",
    "globe-trotter",
}

DAMAGE_ANALYSIS_PROMPT = """You are a baggage damage assessment expert for an airline.
Analyze this luggage damage photo carefully.

Return ONLY a valid JSON object with exactly these fields:
{
  "damage_types": ["list", "of", "damage", "descriptions"],
  "severity_score": 0.0,
  "confidence": 0.0
}

Rules:
- damage_types: list of strings describing each type of damage visible
  (e.g. "cracked shell", "broken wheel", "torn fabric", "dented frame", "missing handle")
  Use empty list [] if no damage is visible.
- severity_score: float between 0.0 and 1.0
  0.0 = no damage / cosmetic only
  0.3 = minor damage (scratches, small dents)
  0.5 = moderate damage (cracked shell, broken handle)
  0.8 = severe damage (large cracks, broken wheels)
  1.0 = destroyed / unusable
- confidence: float between 0.0 and 1.0 — how confident you are in the assessment
  (lower if image is blurry, dark, or the bag is partially visible)

Return ONLY the JSON object. No explanation, no markdown, no code blocks."""

BRAND_CLASSIFICATION_PROMPT = """You are a luxury luggage brand expert.
Analyze this luggage image and identify the brand.

Return ONLY a valid JSON object with exactly these fields:
{
  "brand": "Brand Name or null",
  "is_luxury": false,
  "confidence": 0.0
}

Rules:
- brand: string with the brand name if visible/identifiable, or null if unknown
- is_luxury: true if the brand is a high-end luxury brand (Rimowa, Louis Vuitton, Tumi,
  Brics, Zero Halliburton, Globe-Trotter, Montblanc, Porsche Design),
  false for standard brands (Samsonite, American Tourister, VIP, etc.)
- confidence: float 0.0–1.0 — how confident you are in the brand identification

Return ONLY the JSON object. No explanation, no markdown, no code blocks."""


class GeminiVisionProvider(VisionProvider):
    """
    Gemini Flash vision implementation for damage analysis and brand classification.

    Uses Gemini 2.5 Flash multimodal API to analyze luggage photos.
    POC uses free tier: 1500 requests/day, 1M tokens/day.
    Ref: https://ai.google.dev/pricing

    Future swap: implement YOLOv8VisionProvider in yolov8_vision.py,
    then set VISION_PROVIDER=yolov8 in .env. Zero other changes needed.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        """
        Initialise the Gemini Vision provider.

        Args:
            api_key: Gemini API key from GEMINI_API_KEY env var.
            model: Gemini model name. Defaults to gemini-2.5-flash.
        """
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._model_name = model

    def _load_image(self, image_path: str) -> Image.Image:
        """
        Load an image from disk.

        Args:
            image_path: Absolute or relative path to the image file.

        Returns:
            PIL Image object.

        Raises:
            FileNotFoundError: If the image path does not exist.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        return Image.open(path)

    def _parse_json_response(self, raw_text: str, context: str) -> dict:
        """
        Safely parse a JSON response from Gemini.

        Gemini sometimes wraps JSON in markdown code blocks — this handles that.

        Args:
            raw_text: Raw text response from Gemini.
            context: Context string for logging (e.g. 'analyze_damage').

        Returns:
            Parsed dict from the JSON response.

        Raises:
            ValueError: If the response cannot be parsed as JSON.
        """
        # Strip markdown code blocks if present
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error(
                "gemini_vision_json_parse_failed",
                extra={"context": context, "raw": raw_text[:200], "error": str(exc)},
            )
            raise ValueError(
                f"Gemini returned invalid JSON for {context}: {raw_text[:100]}"
            ) from exc

    async def analyze_damage(self, image_path: str) -> DamageResult:
        """
        Analyse a damage photo and return structured damage assessment.

        Sends the image to Gemini with a structured prompt requesting
        damage_types, severity_score, and confidence as JSON.

        Args:
            image_path: Path to the damage photo (JPG/PNG).

        Returns:
            DamageResult with damage_types list, severity_score (0.0–1.0),
            and confidence (0.0–1.0).
        """
        logger.info(
            "gemini_vision_analyze_damage_started",
            extra={"image": image_path, "model": self._model_name},
        )

        image = self._load_image(image_path)
        response = self._model.generate_content([DAMAGE_ANALYSIS_PROMPT, image])
        parsed = self._parse_json_response(response.text, "analyze_damage")

        result = DamageResult(
            damage_types=parsed.get("damage_types", []),
            severity_score=float(parsed.get("severity_score", 0.0)),
            confidence=float(parsed.get("confidence", 0.0)),
            raw_description=response.text,
        )

        logger.info(
            "gemini_vision_analyze_damage_completed",
            extra={
                "image": image_path,
                "damage_types": result.damage_types,
                "severity_score": result.severity_score,
                "confidence": result.confidence,
            },
        )

        return result

    async def classify_brand(self, image_path: str) -> BrandResult:
        """
        Detect luggage brand from a photo and determine if it is a luxury item.

        Sends the image to Gemini asking for brand identification, then
        cross-checks the detected brand against the LUXURY_BRANDS set.

        Args:
            image_path: Path to the luggage photo (JPG/PNG).

        Returns:
            BrandResult with brand name (or None), is_luxury flag,
            and confidence score (0.0–1.0).
        """
        logger.info(
            "gemini_vision_classify_brand_started",
            extra={"image": image_path, "model": self._model_name},
        )

        image = self._load_image(image_path)
        response = self._model.generate_content([BRAND_CLASSIFICATION_PROMPT, image])
        parsed = self._parse_json_response(response.text, "classify_brand")

        brand_raw = parsed.get("brand")
        brand_name = brand_raw if brand_raw and brand_raw.lower() != "null" else None

        # Cross-check against known luxury brands set
        # Gemini's is_luxury flag + our own set — both must agree for luxury = True
        gemini_says_luxury = bool(parsed.get("is_luxury", False))
        brand_in_luxury_set = (
            brand_name is not None and brand_name.lower() in LUXURY_BRANDS
        )
        is_luxury = gemini_says_luxury or brand_in_luxury_set

        result = BrandResult(
            brand=brand_name,
            is_luxury=is_luxury,
            confidence=float(parsed.get("confidence", 0.0)),
        )

        logger.info(
            "gemini_vision_classify_brand_completed",
            extra={
                "image": image_path,
                "brand": result.brand,
                "is_luxury": result.is_luxury,
                "confidence": result.confidence,
            },
        )

        return result
