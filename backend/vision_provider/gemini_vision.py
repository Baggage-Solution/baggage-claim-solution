from __future__ import annotations

import asyncio
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

# ── Damage analysis prompt — NEUTRAL framing ──────────────────────────────────
# IMPORTANT: The original prompt said "Analyze this luggage DAMAGE photo" which
# primed the model to always find damage. Gemini would then invent scratches,
# dents, or wear on a perfectly fine bag because it was told damage exists.
#
# This prompt is deliberately neutral: it asks the model to first determine
# WHETHER damage is present, and only describe it if it genuinely is.
# The "if the bag appears undamaged" instruction with explicit 0.0 requirements
# is critical — without it the model never returns severity=0 in practice.
DAMAGE_ANALYSIS_PROMPT = """You are a baggage inspection expert for an airline claims department.
Your job is to objectively examine this luggage photo and determine whether the bag has suffered physical damage.

Return ONLY a valid JSON object with exactly these fields:
{
  "damage_types": [],
  "severity_score": 0.0,
  "confidence": 0.0
}

Rules:
- First ask yourself: does this bag show actual physical damage? Look for structural damage only:
  cracked or broken shell, torn or ripped fabric, broken or missing wheels, bent or broken frame,
  broken handle or zipper, deep dents that affect structure, burns or severe staining.
  Do NOT flag: normal wear, minor scuffs, manufacturer patterns, dirt, age marks.

- damage_types: list ONLY actual structural damage visible. Use empty list [] if the bag
  looks intact and undamaged. Do not invent or guess damage.
  Examples: "cracked shell", "broken wheel", "torn fabric", "bent frame", "missing handle"

- severity_score: float 0.0–1.0
  0.0 = no damage visible / bag appears intact / cosmetic marks only
  0.1–0.2 = very minor (small scratches, slight scuffs that do not affect function)
  0.3–0.4 = minor (small dents, minor tears that do not break the bag open)
  0.5–0.6 = moderate (cracked shell, broken handle, significant tear)
  0.7–0.8 = severe (large cracks, broken wheels, major structural failure)
  0.9–1.0 = destroyed / bag is not usable

  CRITICAL: If the bag appears undamaged or has only surface marks, severity_score MUST be 0.0
  or very close to it. Do not assign severity > 0.2 unless there is clear structural damage.

- confidence: float 0.0–1.0 — how confident you are in the assessment.
  Lower if the image is blurry, the bag is partially visible, or lighting is poor.

Return ONLY the JSON object. No explanation, no markdown, no code blocks."""

BRAND_CLASSIFICATION_PROMPT = """You are a luxury luggage brand expert.
Analyze this luggage image and identify the brand if visible.

Return ONLY a valid JSON object with exactly these fields:
{
  "brand": null,
  "is_luxury": false,
  "confidence": 0.0
}

Rules:
- brand: string with the brand name if clearly visible/identifiable, or null if unknown/not visible.
- is_luxury: true only for confirmed high-end luxury brands (Rimowa, Louis Vuitton, Tumi,
  Brics, Zero Halliburton, Globe-Trotter, Montblanc, Porsche Design).
  false for standard brands (Samsonite, American Tourister, VIP, etc.) or if brand is unknown.
- confidence: float 0.0–1.0 — how confident you are in the brand identification.
  0.0 if no brand markings are visible.

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
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._model_name = model

    def _load_image(self, image_path: str) -> Image.Image:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        return Image.open(path)

    def _parse_json_response(self, raw_text: str, context: str) -> dict:
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

    async def _call_with_retry(
        self, prompt: str, image: Image.Image, context: str
    ) -> object:
        """
        Call Gemini with exponential backoff on 429 rate-limit errors.
        Retries up to 3 times: 30s → 60s waits.
        """
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                return self._model.generate_content([prompt, image])
            except Exception as exc:
                err_str = str(exc).lower()
                is_rate_limit = (
                    "429" in str(exc) or "quota" in err_str or "rate" in err_str
                )

                if is_rate_limit and attempt < 2:
                    wait_secs = 30 * (2**attempt)
                    logger.warning(
                        "gemini_vision_rate_limited",
                        extra={
                            "context": context,
                            "attempt": attempt + 1,
                            "wait_secs": wait_secs,
                        },
                    )
                    last_exc = exc
                    await asyncio.sleep(wait_secs)
                else:
                    raise

        raise last_exc

    async def analyze_damage(self, image_path: str) -> DamageResult:
        """
        Examine a luggage photo and objectively determine whether damage is present.

        Uses a neutral prompt that does not assume damage exists. Returns
        damage_types=[] and severity_score=0.0 for undamaged bags.
        Retries up to 3 times on 429 rate-limit errors.
        """
        logger.info(
            "gemini_vision_analyze_damage_started",
            extra={"image": image_path, "model": self._model_name},
        )

        image = self._load_image(image_path)
        response = await self._call_with_retry(
            DAMAGE_ANALYSIS_PROMPT, image, "analyze_damage"
        )
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
        Detect luggage brand and determine if it is a luxury item.
        Retries up to 3 times on 429 rate-limit errors.
        """
        logger.info(
            "gemini_vision_classify_brand_started",
            extra={"image": image_path, "model": self._model_name},
        )

        image = self._load_image(image_path)
        response = await self._call_with_retry(
            BRAND_CLASSIFICATION_PROMPT, image, "classify_brand"
        )
        parsed = self._parse_json_response(response.text, "classify_brand")

        brand_raw = parsed.get("brand")
        brand_name = brand_raw if brand_raw and brand_raw.lower() != "null" else None

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
