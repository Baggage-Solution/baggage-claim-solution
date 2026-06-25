from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from PIL import Image

from backend.ocr_provider.base import OCRProvider, TagData

logger = logging.getLogger(__name__)

# Bedrock's Anthropic Messages API version — a protocol version, not a model
# version. Fixed by AWS for all Claude-on-Bedrock InvokeModel calls.
BEDROCK_ANTHROPIC_VERSION = "bedrock-2023-05-31"

# ── Validation patterns ────────────────────────────────────────────────────────
# Identical to GeminiOCRProvider's patterns — same IATA-standard formats
# regardless of which vision model extracted the text, so downstream
# agents see identical TagData shapes from either provider.
PNR_PATTERN = re.compile(r"^[A-Z0-9]{6}$")
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


class BedrockOCRProvider(OCRProvider):
    """
    AWS Bedrock (Claude multimodal) OCR implementation for airline bag tag
    data extraction (Production).

    Uses the same Bedrock Claude model as BedrockVisionProvider — no extra
    AWS resource needed beyond Bedrock model access already granted for
    BedrockLLMProvider/BedrockVisionProvider.

    Image handling and retry logic mirror BedrockVisionProvider exactly
    (base64-encoded image in the Messages API request, throttling retry
    with backoff) since both talk to the same Bedrock InvokeModel API.

    Future swap: set OCR_PROVIDER=paddleocr → paddleocr.py runs fully
    offline with no PII sent to any external API. Zero other changes needed.
    """

    def __init__(self, model_id: str, region: str) -> None:
        """
        Initialise the Bedrock OCR provider.

        Args:
            model_id: Bedrock model ID for Claude (e.g.
                "anthropic.claude-sonnet-4-20250514-v1:0"). Read from
                Settings.bedrock_ocr_model — never hardcoded.
            region: AWS region the Bedrock endpoint lives in (e.g. us-east-1).
        """
        self._model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def _load_image_base64(self, image_path: str) -> tuple[str, str]:
        """
        Load a bag tag image from disk and base64-encode it for Claude's
        Messages API.

        Identical approach to BedrockVisionProvider._load_image_base64 —
        reads raw bytes with a context manager, detects the real format via
        PIL (not the file extension), and base64-encodes for the request body.

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
            raise FileNotFoundError(f"Bag tag image not found: {image_path}")

        with open(path, "rb") as fh:
            data = fh.read()

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

    def _parse_json_response(self, raw_text: str) -> dict:
        """
        Safely parse a JSON response from Claude.

        Claude sometimes wraps JSON in markdown code blocks — strips them
        first, same as GeminiOCRProvider.

        Args:
            raw_text: Raw text content block from Claude's response.

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
                "bedrock_ocr_json_parse_failed",
                extra={"raw": raw_text[:200], "error": str(exc)},
            )
            raise ValueError(
                f"Bedrock OCR returned invalid JSON: {raw_text[:100]}"
            ) from exc

    def _validate_pnr(self, pnr: Optional[str]) -> Optional[str]:
        """
        Validate PNR format: exactly 6 uppercase alphanumeric characters.

        Args:
            pnr: Raw PNR string from Claude's response.

        Returns:
            Uppercased PNR if valid, None otherwise.
        """
        if not pnr:
            return None
        cleaned = str(pnr).strip().upper()
        if PNR_PATTERN.match(cleaned):
            return cleaned
        logger.warning(
            "bedrock_ocr_invalid_pnr",
            extra={"pnr": pnr, "expected_pattern": r"[A-Z0-9]{6}"},
        )
        return None

    def _validate_bag_id(self, bag_id: Optional[str]) -> Optional[str]:
        """
        Validate bag ID format: 10–12 continuous digits.

        Strips spaces before validation — real airline tags often print the
        number with spaces (e.g. "0452 30 674234") but the underlying IATA
        number is a continuous digit string.

        Args:
            bag_id: Raw bag ID string from Claude's response.

        Returns:
            Space-stripped digit string if valid (10–12 digits), None otherwise.
        """
        if not bag_id:
            return None
        cleaned = str(bag_id).strip().replace(" ", "")
        if BAG_ID_PATTERN.match(cleaned):
            return cleaned
        logger.warning(
            "bedrock_ocr_invalid_bag_id",
            extra={"bag_id": bag_id, "expected_pattern": r"\d{10,12}"},
        )
        return None

    async def _call_with_retry(self, image_path: str) -> str:
        """
        Call Bedrock InvokeModel with the bag tag image, with retry on
        throttling.

        Args:
            image_path: Path to the bag tag image.

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
                        {"type": "text", "text": BAG_TAG_EXTRACTION_PROMPT},
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
                    raise ValueError("Bedrock OCR returned no text content")
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
                        "bedrock_ocr_throttled",
                        extra={
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

    async def extract_bag_tag(self, image_path: str) -> TagData:
        """
        Extract flight number, PNR, and bag ID from a bag tag photo.

        Sends the image to Bedrock Claude with a structured extraction
        prompt, parses the JSON response, and validates all field formats
        with regex — same validation rules as GeminiOCRProvider, so
        downstream agents (A3) see identical TagData behaviour regardless
        of OCR_PROVIDER.

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
            "bedrock_ocr_extract_tag_started",
            extra={"image": image_path, "model": self._model_id},
        )

        try:
            raw_text = await self._call_with_retry(image_path)
            parsed = self._parse_json_response(raw_text)

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
                "bedrock_ocr_extract_tag_completed",
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
                "bedrock_ocr_extract_tag_failed",
                extra={"image": image_path, "error": str(exc)},
            )
            return TagData(confidence=0.0)