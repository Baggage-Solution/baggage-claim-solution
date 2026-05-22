from __future__ import annotations

import logging

from backend.vision_provider.base import BrandResult, DamageResult, VisionProvider

logger = logging.getLogger(__name__)

LUXURY_BRANDS = {"rimowa", "louis vuitton", "tumi", "brics", "zero halliburton", "globe-trotter"}


class GeminiVisionProvider(VisionProvider):
    """
    Gemini Flash vision implementation (POC — free tier, 1500 req/day).
    https://ai.google.dev/pricing

    Future swap: implement YOLOv8VisionProvider in yolov8_vision.py,
    then set VISION_PROVIDER=yolov8 in .env. Zero other changes.
    """

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._model_name = model

    async def analyze_damage(self, image_path: str) -> DamageResult:
        # TODO (T-006):
        # 1. Load image from image_path (PIL.Image or bytes)
        # 2. Build prompt: "Analyse this luggage damage photo. Return JSON with:
        #      damage_types (list), severity_score (0.0-1.0), confidence (0.0-1.0)"
        # 3. Call self._model.generate_content([prompt, image])
        # 4. Parse JSON response → DamageResult
        # 5. Log component + confidence for monitoring
        logger.info("gemini_vision_analyze_damage", extra={"image": image_path})
        return DamageResult(damage_types=["stub"], severity_score=0.0, confidence=0.0)

    async def classify_brand(self, image_path: str) -> BrandResult:
        # TODO (T-006):
        # 1. Build prompt: "What brand is this luggage? Is it a luxury brand?
        #      Return JSON: brand (str or null), is_luxury (bool), confidence (0.0-1.0)"
        # 2. Call self._model.generate_content([prompt, image])
        # 3. Parse JSON → BrandResult
        # 4. Cross-check brand.lower() against LUXURY_BRANDS set
        logger.info("gemini_vision_classify_brand", extra={"image": image_path})
        return BrandResult(brand=None, is_luxury=False, confidence=0.0)
