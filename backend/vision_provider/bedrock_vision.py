from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from PIL import Image

from backend.vision_provider.base import (
    BrandResult,
    DamageResult,
    SceneResult,
    VisionProvider,
)

logger = logging.getLogger(__name__)

# Bedrock's Anthropic Messages API version — a protocol version, not a model
# version. Fixed by AWS for all Claude-on-Bedrock InvokeModel calls.
BEDROCK_ANTHROPIC_VERSION = "bedrock-2023-05-31"

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
# Identical content to GeminiVisionProvider's SCENE_ANALYSIS_PROMPT — same
# four questions (object gate, damage, brand, tag presence) answered in ONE
# Claude call. Keeping the prompt text consistent across providers means the
# decision-engine downstream behaves the same regardless of which provider
# is configured, which matters for swap-testing between Gemini and Bedrock.
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
# single-purpose methods directly — identical text to GeminiVisionProvider's
# DAMAGE_ANALYSIS_PROMPT / BRAND_CLASSIFICATION_PROMPT.
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


class BedrockVisionProvider(VisionProvider):
    """
    AWS Bedrock (Claude multimodal) vision implementation (Production).

    Primary method analyze_image() does the full scene analysis (object gate
    + damage + brand + tag presence) in a SINGLE Claude call, mirroring
    GeminiVisionProvider's design exactly — same prompt text, same SceneResult
    shape, same is_bag gate semantics — so swapping VISION_PROVIDER between
    gemini and bedrock changes nothing about downstream agent behaviour.

    analyze_damage() / classify_brand() are retained as thin wrappers for
    backwards compatibility with existing unit tests, same as the Gemini
    implementation.

    Image handling: Claude's Messages API takes images as base64-encoded
    bytes in the request body (no file upload step, unlike Gemini's SDK
    which accepts a PIL Image object directly) — _load_image_base64() reads
    the file once and returns both the base64 string and the detected
    media type for the request body.
    """

    def __init__(self, model_id: str, region: str) -> None:
        """
        Initialise the Bedrock vision provider.

        Args:
            model_id: Bedrock model ID for Claude (e.g.
                "anthropic.claude-sonnet-4-20250514-v1:0"). Read from
                Settings.bedrock_vision_model — never hardcoded.
            region: AWS region the Bedrock endpoint lives in (e.g. us-east-1).
        """
        self._model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def _load_image_base64(self, image_path: str) -> tuple[str, str]:
        """
        Load an image from disk and base64-encode it for Claude's Messages API.

        Reads raw bytes with a context manager (same WinError-32-avoidance
        pattern as GeminiVisionProvider — closes the OS file handle before
        returning rather than relying on garbage collection), then opens
        with PIL only to detect the real format (so a mislabelled extension
        doesn't send the wrong media_type to Claude).

        Args:
            image_path: Absolute or relative path to the image file.

        Returns:
            Tuple of (base64_data, media_type) — e.g.
            ("/9j/4AAQ...", "image/jpeg").

        Raises:
            FileNotFoundError: If the image path does not exist.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        with open(path, "rb") as fh:
            data = fh.read()

        # Detect actual format via PIL rather than trusting the file
        # extension — a mislabelled .jpg that's actually a PNG would
        # otherwise send an incorrect media_type to Claude.
        img = Image.open(io.BytesIO(data))
        img.load()
        pil_format = (img.format or "JPEG").upper()
        media_type = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
        }.get(pil_format, "image/jpeg")

        encoded = base64.b64encode(data).decode("utf-8")
        return encoded, media_type

    def _parse_json_response(self, raw_text: str, context: str) -> dict:
        """Parse a JSON object out of Claude's text reply.

        Claude sometimes wraps JSON in markdown code fences despite being
        told not to — strip them before parsing, same as GeminiVisionProvider.

        Args:
            raw_text: Raw text content block from Claude's response.
            context: Label for logging (e.g. "analyze_image").

        Returns:
            Parsed dict.

        Raises:
            ValueError: If the response cannot be parsed as valid JSON.
        """
        import re

        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error(
                "bedrock_vision_json_parse_failed",
                extra={"context": context, "raw": raw_text[:200], "error": str(exc)},
            )
            raise ValueError(
                f"Bedrock vision returned invalid JSON for {context}: {raw_text[:100]}"
            ) from exc

    async def _call_with_retry(self, prompt: str, image_path: str, context: str) -> str:
        """
        Call Bedrock InvokeModel with an image + text prompt, with retry on
        throttling.

        boto3 is synchronous, so the network call is offloaded via
        asyncio.to_thread — same pattern as BedrockLLMProvider (P-003) and
        S3StorageProvider (P-004).

        Args:
            prompt: Text prompt to send alongside the image.
            image_path: Path to the image file to analyse.
            context: Label for logging (e.g. "analyze_image").

        Returns:
            The text content of Claude's reply.

        Raises:
            ValueError: If Claude returns no text content block.
            Exception: Re-raises after all retries are exhausted, or
                immediately for non-throttling errors.
        """
        base64_data, media_type = self._load_image_base64(image_path)

        body = {
            "anthropic_version": BEDROCK_ANTHROPIC_VERSION,
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_data,
                            },
                        },
                    ],
                }
            ],
        }

        last_exc: Optional[Exception] = None

        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    self._client.invoke_model,
                    modelId=self._model_id,
                    body=json.dumps(body),
                )
                response_body = json.loads(response["body"].read())
                content_blocks = response_body.get("content", [])
                text = "".join(
                    block.get("text", "")
                    for block in content_blocks
                    if block.get("type") == "text"
                )
                if not text:
                    raise ValueError(
                        f"Bedrock vision returned no text content for {context}"
                    )
                return text
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "")
                is_throttled = error_code in (
                    "ThrottlingException",
                    "ServiceQuotaExceededException",
                    "TooManyRequestsException",
                )
                if is_throttled and attempt < 2:
                    wait_secs = 30 * (2**attempt)
                    logger.warning(
                        "bedrock_vision_throttled",
                        extra={
                            "context": context,
                            "attempt": attempt + 1,
                            "wait_secs": wait_secs,
                            "error_code": error_code,
                        },
                    )
                    last_exc = exc
                    await asyncio.sleep(wait_secs)
                else:
                    raise

        raise last_exc

    def _resolve_luxury(
        self, brand_name: Optional[str], claude_says_luxury: bool
    ) -> bool:
        """Resolve final is_luxury flag, falling back to the static brand set
        if Claude's own is_luxury judgement disagrees. Identical logic to
        GeminiVisionProvider._resolve_luxury for behavioural parity.

        Args:
            brand_name: Detected brand name, or None.
            claude_says_luxury: Claude's own is_luxury field from the response.

        Returns:
            True if either Claude flagged it luxury or the brand is in the
            known LUXURY_BRANDS set.
        """
        brand_in_luxury_set = (
            brand_name is not None and brand_name.lower() in LUXURY_BRANDS
        )
        return bool(claude_says_luxury) or brand_in_luxury_set

    async def analyze_image(self, image_path: str) -> SceneResult:
        """
        Single-pass scene analysis: object gate + damage + brand + tag presence.

        Args:
            image_path: Path to the photo to analyse.

        Returns:
            SceneResult populated from Claude's structured JSON response.
        """
        logger.info(
            "bedrock_vision_analyze_image_started",
            extra={"image": image_path, "model": self._model_id},
        )

        raw_text = await self._call_with_retry(
            SCENE_ANALYSIS_PROMPT, image_path, "analyze_image"
        )
        parsed = self._parse_json_response(raw_text, "analyze_image")

        brand_raw = parsed.get("brand")
        brand_name = (
            brand_raw if brand_raw and str(brand_raw).lower() != "null" else None
        )
        is_bag = bool(parsed.get("is_bag", False))

        # If the model says it is NOT a bag, force damage/brand to neutral so
        # a non-bag image can never be mistaken for an intact bag downstream.
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
            raw_description=raw_text,
        )

        logger.info(
            "bedrock_vision_analyze_image_completed",
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
        """Backwards-compatible damage-only path (used by existing unit tests).

        Args:
            image_path: Path to the photo to analyse.

        Returns:
            DamageResult populated from Claude's structured JSON response.
        """
        logger.info(
            "bedrock_vision_analyze_damage_started",
            extra={"image": image_path, "model": self._model_id},
        )
        raw_text = await self._call_with_retry(
            DAMAGE_ANALYSIS_PROMPT, image_path, "analyze_damage"
        )
        parsed = self._parse_json_response(raw_text, "analyze_damage")
        result = DamageResult(
            damage_types=parsed.get("damage_types", []),
            severity_score=float(parsed.get("severity_score", 0.0)),
            confidence=float(parsed.get("confidence", 0.0)),
            raw_description=raw_text,
        )
        logger.info(
            "bedrock_vision_analyze_damage_completed",
            extra={
                "image": image_path,
                "damage_types": result.damage_types,
                "severity_score": result.severity_score,
                "confidence": result.confidence,
            },
        )
        return result

    async def classify_brand(self, image_path: str) -> BrandResult:
        """Backwards-compatible brand-only path (used by existing unit tests).

        Args:
            image_path: Path to the photo to analyse.

        Returns:
            BrandResult populated from Claude's structured JSON response.
        """
        logger.info(
            "bedrock_vision_classify_brand_started",
            extra={"image": image_path, "model": self._model_id},
        )
        raw_text = await self._call_with_retry(
            BRAND_CLASSIFICATION_PROMPT, image_path, "classify_brand"
        )
        parsed = self._parse_json_response(raw_text, "classify_brand")
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
            "bedrock_vision_classify_brand_completed",
            extra={
                "image": image_path,
                "brand": result.brand,
                "is_luxury": result.is_luxury,
                "confidence": result.confidence,
            },
        )
        return result