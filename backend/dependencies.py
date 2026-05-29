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
    s = get_settings()
    if s.llm_provider == "gemini":
        from backend.llm_provider.gemini_llm import GeminiLLMProvider
        return GeminiLLMProvider(api_key=s.gemini_api_key, model=s.gemini_model)
    raise ValueError(f"Unknown LLM_PROVIDER: {s.llm_provider}")


# ──────────────────────────────────────────────────────────────
# VISION PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_vision():
    s = get_settings()
    if s.vision_provider == "gemini":
        from backend.vision_provider.gemini_vision import GeminiVisionProvider
        return GeminiVisionProvider(api_key=s.gemini_api_key, model=s.gemini_vision_model)
    raise ValueError(f"Unknown VISION_PROVIDER: {s.vision_provider}")


# ──────────────────────────────────────────────────────────────
# OCR PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_ocr():
    s = get_settings()
    if s.ocr_provider == "gemini":
        from backend.ocr_provider.gemini_ocr import GeminiOCRProvider
        return GeminiOCRProvider(api_key=s.gemini_api_key, model=s.gemini_vision_model)
    raise ValueError(f"Unknown OCR_PROVIDER: {s.ocr_provider}")


# ──────────────────────────────────────────────────────────────
# DATABASE PROVIDER  — module-level singleton with reset-on-failure
# ──────────────────────────────────────────────────────────────
#
# Design rationale
# ----------------
# We need exactly ONE SupabaseDBProvider instance alive for the whole process
# so its internal httpx.AsyncClient connection pool is reused across requests
# (warm TCP connections, no repeated DNS lookups, no getaddrinfo races).
#
# We cannot use @lru_cache because:
#   - lru_cache caches the return value at call time.
#   - SupabaseDBProvider.__init__ is synchronous and never raises even for a
#     bad URL — it just stores credentials.
#   - The actual network call happens later inside _get_client() (async).
#   - If that first network call fails, lru_cache still holds the broken
#     instance forever — no way to recover without restarting the server.
#
# Solution: keep a plain module-level variable (_db_instance). provide_db()
# creates the instance on first call and reuses it on every subsequent call
# (same behaviour as lru_cache). SupabaseDBProvider._get_client() now resets
# self._client = None on any connection error so the next call retries the
# handshake rather than reusing a dead httpx session.
#
_db_instance = None


def provide_db():
    """
    Return the shared SupabaseDBProvider singleton, creating it on first call.

    Returns None if Supabase credentials are missing or invalid — all callers
    (A4, /claims/pending, /decision, /claims/{id}/status) guard for None and
    degrade gracefully instead of crashing.
    """
    global _db_instance

    if _db_instance is not None:
        return _db_instance

    s = get_settings()

    if s.db_provider != "supabase":
        raise ValueError(f"Unknown DB_PROVIDER: {s.db_provider}")

    if not s.supabase_url or not s.supabase_service_role_key:
        logger.warning(
            "provide_db: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set — "
            "DB persistence disabled."
        )
        return None

    placeholder_fragments = ("<YOUR_PROJECT_REF>", "<YOUR_SUPABASE", "YOUR_PROJECT")
    if any(p in s.supabase_url for p in placeholder_fragments):
        logger.warning(
            "provide_db: SUPABASE_URL still contains placeholder '%s' — "
            "DB persistence disabled.",
            s.supabase_url,
        )
        return None

    try:
        from backend.db.supabase_client import SupabaseDBProvider
        _db_instance = SupabaseDBProvider(
            url=s.supabase_url,
            service_role_key=s.supabase_service_role_key,
        )
        logger.info("provide_db: SupabaseDBProvider singleton created")
        return _db_instance
    except Exception as exc:
        logger.error("provide_db: failed to create SupabaseDBProvider — %s", exc)
        return None


# ──────────────────────────────────────────────────────────────
# STORAGE PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_storage():
    s = get_settings()
    if s.storage_provider == "local":
        from backend.storage_provider.local_storage import LocalStorageProvider
        return LocalStorageProvider(base_path=s.local_storage_base_path)
    raise ValueError(f"Unknown STORAGE_PROVIDER: {s.storage_provider}")