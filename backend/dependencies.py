from __future__ import annotations

import logging
from functools import lru_cache

from backend.config import get_settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# LLM PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_llm():
    """Instantiate and cache the configured LLM provider.

    Reads LLM_PROVIDER from settings to select the concrete implementation.
    Add new providers by extending this function and implementing LLMProvider ABC.

    Returns:
        LLMProvider: The active LLM provider instance.

    Raises:
        ValueError: If LLM_PROVIDER is set to an unknown value.
    """
    s = get_settings()
    if s.llm_provider == "gemini":
        from backend.llm_provider.gemini_llm import GeminiLLMProvider

        return GeminiLLMProvider(api_key=s.gemini_api_key, model=s.gemini_model)
    raise ValueError(
        f"Unknown LLM_PROVIDER: {s.llm_provider}. Implement the provider and add it here."
    )


# ──────────────────────────────────────────────────────────────
# VISION PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_vision():
    """Instantiate and cache the configured vision provider.

    Reads VISION_PROVIDER from settings. Swap to YOLOv8 by setting
    VISION_PROVIDER=yolov8 and implementing yolov8_vision.py.

    Returns:
        VisionProvider: The active vision provider instance.

    Raises:
        ValueError: If VISION_PROVIDER is set to an unknown value.
    """
    s = get_settings()
    if s.vision_provider == "gemini":
        from backend.vision_provider.gemini_vision import GeminiVisionProvider

        return GeminiVisionProvider(
            api_key=s.gemini_api_key, model=s.gemini_vision_model
        )
    raise ValueError(f"Unknown VISION_PROVIDER: {s.vision_provider}")


# ──────────────────────────────────────────────────────────────
# OCR PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_ocr():
    """Instantiate and cache the configured OCR provider.

    Reads OCR_PROVIDER from settings. Swap to PaddleOCR by setting
    OCR_PROVIDER=paddleocr and implementing paddleocr_ocr.py.

    Returns:
        OCRProvider: The active OCR provider instance.

    Raises:
        ValueError: If OCR_PROVIDER is set to an unknown value.
    """
    s = get_settings()
    if s.ocr_provider == "gemini":
        from backend.ocr_provider.gemini_ocr import GeminiOCRProvider

        return GeminiOCRProvider(api_key=s.gemini_api_key, model=s.gemini_vision_model)
    raise ValueError(f"Unknown OCR_PROVIDER: {s.ocr_provider}")


# ──────────────────────────────────────────────────────────────
# DATABASE PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_db():
    """Instantiate and cache the configured database provider.

    Reads DB_PROVIDER from settings. Backed by Supabase for the POC;
    swap to any PostgreSQL by implementing a new DBProvider subclass.

    Returns:
        DBProvider | None: The active database provider instance, or None if
        credentials are missing/invalid (POC graceful degradation — agents
        continue without persistence rather than crashing the whole request).

    Raises:
        ValueError: If DB_PROVIDER is set to an unknown value.
    """
    s = get_settings()
    if s.db_provider == "supabase":
        # Guard: if credentials are placeholder / missing, return None so the
        # backend starts cleanly and agents degrade gracefully instead of
        # crashing with ValueError or a DNS error on every request.
        if not s.supabase_url or not s.supabase_service_role_key:
            logger.warning(
                "provide_db: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set — "
                "DB persistence disabled. Set credentials in .env to enable."
            )
            return None

        placeholder_fragments = ("<YOUR_PROJECT_REF>", "<YOUR_SUPABASE", "YOUR_PROJECT")
        if any(p in s.supabase_url for p in placeholder_fragments):
            logger.warning(
                "provide_db: SUPABASE_URL still contains placeholder value '%s' — "
                "DB persistence disabled. Replace with your real project URL.",
                s.supabase_url,
            )
            return None

        try:
            from backend.db.supabase_client import SupabaseDBProvider

            return SupabaseDBProvider(
                url=s.supabase_url, service_role_key=s.supabase_service_role_key
            )
        except Exception as exc:
            logger.error(
                "provide_db: failed to initialise Supabase client — "
                "DB persistence disabled. Error: %s",
                exc,
            )
            return None

    raise ValueError(f"Unknown DB_PROVIDER: {s.db_provider}")


# ──────────────────────────────────────────────────────────────
# STORAGE PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_storage():
    """Instantiate and cache the configured storage provider.

    Reads STORAGE_PROVIDER from settings. Defaults to local disk for POC;
    swap to Cloudflare R2 or S3 by setting STORAGE_PROVIDER=r2/s3.

    Returns:
        StorageProvider: The active storage provider instance.

    Raises:
        ValueError: If STORAGE_PROVIDER is set to an unknown value.
    """
    s = get_settings()
    if s.storage_provider == "local":
        from backend.storage_provider.local_storage import LocalStorageProvider

        return LocalStorageProvider(base_path=s.local_storage_base_path)
    raise ValueError(f"Unknown STORAGE_PROVIDER: {s.storage_provider}")
