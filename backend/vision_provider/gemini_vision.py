from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from pathlib import Path

from PIL import Image

from backend.vision_provider.base import (BrandResult, DamageResult,
                                          SceneResult, VisionProvider)

logger = logging.getLogger(__name__)

LUXURY_BRANDS = {
    "rimowa",
    "louis vuitton",
    "tumi",
    "brics",
    "zero halliburton",
    "globe-trotter",
    "montblanc",
    "porsche design",
}

# ── Combined scene-analysis prompt ────────────────────────────────────────────
# ONE Gemini call answers everything the pipeline needs about an image:
#   - is it luggage at all? (object gate → fixes non-bag uploads, issue #1)
#   - is it damaged, how badly?
#   - what brand / luxury?
#   - is a readable bag tag visible in the frame? (→ enables OCR on the same
#     image, fixing "both in one photo" and "both uploaded together", #2/#4)
#
# The prompt is deliberately NEUTRAL about damage: it must be willing to return
# no damage on an intact bag, and must NOT call a non-bag object a bag.
SCENE_ANALYSIS_PROMPT = """You are a baggage inspection expert for an airline claims department.
Examine this single photo and report what you objectively see. Do not assume it shows a suitcase.

Return ONLY a valid JSON object with exactly these fields:
{
  "is_bag": true,
  "bag_confidence": 0.0,
  "object_description": "",
  "damage_types": [],
  "severity_score": 0.0,
  "damage_confidence": 0.0,
  "brand": null,
  "is_luxury": false,
  "brand_confidence": 0.0,
  "tag_visible": false,
  "tag_confidence": 0.0
}

Field rules:

OBJECT GATE (most important — do this first):
- is_bag: true ONLY if the main subject is a piece of luggage / baggage —
  a suitcase, trolley bag, duffel, backpack, travel bag, hard-shell case, etc.
  false for anything else (a watch, phone, person, document, food, room, car,
  random object, screenshot, etc.).
- bag_confidence: 0.0–1.0, how sure you are about the is_bag decision.
- object_description: 2–5 words naming what you actually see
  (e.g. "black hard-shell suitcase", "wristwatch", "person standing", "ID card").

DAMAGE (only meaningful if is_bag is true; if is_bag is false set these to empty/0.0):
- damage_types: list ONLY actual STRUCTURAL damage visible: "cracked shell",
  "broken wheel", "torn fabric", "bent frame", "broken handle", "broken zipper",
  "deep dent", "burn", "severe stain". Use [] if the bag looks intact.
  Do NOT flag normal wear, minor scuffs, manufacturer patterns, dirt, or age.
- severity_score: 0.0–1.0.
  0.0 = intact / cosmetic only; 0.1–0.2 = very minor scratches;
  0.3–0.4 = minor dents/small tears; 0.5–0.6 = cracked shell/broken handle;
  0.7–0.8 = broken wheels/major structural failure; 0.9–1.0 = destroyed.
  If the bag appears undamaged, severity_score MUST be 0.0 or very close.
- damage_confidence: 0.0–1.0, lower if blurry/partial/poor lighting.

BRAND (only meaningful if is_bag is true):
- brand: brand name if a logo/marking is clearly visible, else null.
- is_luxury: true only for confirmed high-end brands (Rimowa, Louis Vuitton,
  Tumi, Brics, Zero Halliburton, Globe-Trotter, Montblanc, Porsche Design).
- brand_confidence: 0.0–1.0; 0.0 if no brand markings visible.

BAG TAG PRESENCE:
- tag_visible: true if an AIRLINE BAGGAGE TAG is visible in this photo — the
  printed paper/sticker label (usually white) wrapped on the handle showing a
  barcode and/or a flight number and bag number. Only true if it looks legible
  enough that text could plausibly be read from it.
- tag_confidence: 0.0–1.0, how legible the tag text appears. 0.0 if no tag.

Return ONLY the JSON object. No explanation, no markdown, no code blocks."""

# Kept for backwards compatibility with existing unit tests that call the
# single-purpose methods directly.
DAMAGE_ANALYSIS_PROMPT = """You are a baggage inspection expert for an airline claims department.
Objectively examine this luggage photo and determine whether the bag has physical damage.

Return ONLY a valid JSON object with exactly these fields:
{"damage_types": [], "severity_score": 0.0, "confidence": 0.0}

- damage_types: list ONLY actual structural damage (cracked shell, broken wheel,
  torn fabric, bent frame, broken handle). Empty list [] if intact. Do not invent damage.
- severity_score: 0.0 (intact/cosmetic) to 1.0 (destroyed). If undamaged, MUST be 0.0.
- confidence: 0.0–1.0, lower if blurry or partially visible.

Return ONLY the JSON object. No markdown, no code blocks."""

BRAND_CLASSIFICATION_PROMPT = """You are a luxury luggage brand expert.
Identify the luggage brand if visible.

Return ONLY a valid JSON object with exactly these fields:
{"brand": null, "is_luxury": false, "confidence": 0.0}

- brand: brand name if clearly visible, else null.
- is_luxury: true only for Rimowa, Louis Vuitton, Tumi, Brics, Zero Halliburton,
  Globe-Trotter, Montblanc, Porsche Design. false otherwise.
- confidence: 0.0–1.0; 0.0 if no markings visible.

Return ONLY the JSON object. No markdown, no code blocks."""


class GeminiVisionProvider(VisionProvider):
    """
    Gemini Flash vision implementation.

    Primary method analyze_image() does the full scene analysis (object gate +
    damage + brand + tag presence) in a SINGLE Gemini call — cheaper and more
    consistent than the old two-call (damage + brand) approach, and it adds the
    is_bag gate and tag_visible signal the pipeline now relies on.

    analyze_damage() / classify_brand() are retained as thin wrappers for
    backwards compatibility with existing unit tests.

    BUG FIX (_load_image): Image.open(path) was called without a context manager,
    leaving the OS file handle open until Python GC collected the PIL object.
    On Windows this caused WinError 32 ("file is being used by another process")
    when _move_pending_uploads() tried to move the same file immediately after
    the vision call. Fix: read raw bytes with a context manager so the handle is
    closed before we return, then open from an in-memory BytesIO buffer.

    BUG FIX (_call_with_retry): uses generate_content_async() instead of the
    synchronous generate_content(), so the FastAPI event loop is never blocked
    while waiting for Gemini responses.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._model_name = model

    def _load_image(self, image_path: str) -> Image.Image:
        """
        Load an image from disk for Gemini multimodal input.

        Reads the raw bytes into memory with a context manager (so the OS file
        handle is closed immediately), then opens the image from an in-memory
        BytesIO buffer and calls .load() to force full pixel decode.

        This pattern eliminates WinError 32 ("The process cannot access the
        file because it is being used by another process") which occurred when
        _move_pending_uploads() called shutil.move() on the same file while PIL
        still held an open handle from a bare Image.open(path) call.

        Args:
            image_path: Absolute or relative path to the image file.

        Returns:
            PIL Image object (fully decoded, no open OS file handle).

        Raises:
            FileNotFoundError: If the image path does not exist.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        # Read all bytes then close the file handle before returning.
        # Image.open() on a plain Path keeps the handle open until GC —
        # that causes WinError 32 when shutil.move runs on Windows.
        with open(path, "rb") as fh:
            data = fh.read()
        img = Image.open(io.BytesIO(data))
        img.load()  # force full decode; BytesIO stays alive with the Image object
        return img

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
        Call Gemini generate_content_async with exponential backoff on 429 errors.

        BUG FIX: previously used self._model.generate_content() (synchronous),
        which blocked the FastAPI event loop on every vision call. Now uses
        generate_content_async() to keep the event loop free.

        Args:
            prompt: Text prompt to send alongside the image.
            image: PIL Image to analyse.
            context: Label for logging (e.g. "analyze_image").

        Returns:
            Gemini response object.
        """
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                # ✅ FIXED: async call — does not block the event loop
                return await self._model.generate_content_async([prompt, image])
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

    def _resolve_luxury(self, brand_name, gemini_says_luxury: bool) -> bool:
        brand_in_luxury_set = (
            brand_name is not None and brand_name.lower() in LUXURY_BRANDS
        )
        return bool(gemini_says_luxury) or brand_in_luxury_set

    async def analyze_image(self, image_path: str) -> SceneResult:
        """
        Single-pass scene analysis: object gate + damage + brand + tag presence.
        """
        logger.info(
            "gemini_vision_analyze_image_started",
            extra={"image": image_path, "model": self._model_name},
        )

        image = self._load_image(image_path)
        response = await self._call_with_retry(
            SCENE_ANALYSIS_PROMPT, image, "analyze_image"
        )
        parsed = self._parse_json_response(response.text, "analyze_image")

        brand_raw = parsed.get("brand")
        brand_name = (
            brand_raw if brand_raw and str(brand_raw).lower() != "null" else None
        )
        is_bag = bool(parsed.get("is_bag", False))

        # If the model says it is NOT a bag, force damage/brand to neutral so a
        # non-bag image can never be mistaken for an intact bag downstream.
        damage_types = parsed.get("damage_types", []) if is_bag else []
        severity = float(parsed.get("severity_score", 0.0)) if is_bag else 0.0

        result = SceneResult(
            is_bag=is_bag,
            bag_confidence=float(parsed.get("bag_confidence", 0.0)),
            object_description=str(parsed.get("object_description", "") or ""),
            damage_types=damage_types,
            severity_score=severity,
            damage_confidence=float(parsed.get("damage_confidence", 0.0)),
            brand=brand_name if is_bag else None,
            is_luxury=(
                self._resolve_luxury(brand_name, parsed.get("is_luxury", False))
                if is_bag
                else False
            ),
            brand_confidence=float(parsed.get("brand_confidence", 0.0)),
            tag_visible=bool(parsed.get("tag_visible", False)),
            tag_confidence=float(parsed.get("tag_confidence", 0.0)),
            raw_description=response.text,
        )

        logger.info(
            "gemini_vision_analyze_image_completed",
            extra={
                "image": image_path,
                "is_bag": result.is_bag,
                "bag_confidence": result.bag_confidence,
                "object": result.object_description,
                "damage_types": result.damage_types,
                "severity_score": result.severity_score,
                "tag_visible": result.tag_visible,
                "tag_confidence": result.tag_confidence,
            },
        )
        return result

    async def analyze_damage(self, image_path: str) -> DamageResult:
        """Backwards-compatible damage-only path (used by existing unit tests)."""
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
        """Backwards-compatible brand-only path (used by existing unit tests)."""
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
        brand_name = (
            brand_raw if brand_raw and str(brand_raw).lower() != "null" else None
        )
        result = BrandResult(
            brand=brand_name,
            is_luxury=self._resolve_luxury(brand_name, parsed.get("is_luxury", False)),
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
