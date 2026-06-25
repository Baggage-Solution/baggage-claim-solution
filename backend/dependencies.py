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
    if s.llm_provider == "bedrock":
        from backend.llm_provider.bedrock_llm import BedrockLLMProvider

        return BedrockLLMProvider(
            model_id=s.bedrock_llm_model,
            region=s.aws_region,
            temperature=s.llm_default_temperature,
            max_output_tokens=s.llm_max_output_tokens,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {s.llm_provider}")


# ──────────────────────────────────────────────────────────────
# VISION PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_vision():
    s = get_settings()
    if s.vision_provider == "gemini":
        from backend.vision_provider.gemini_vision import GeminiVisionProvider

        return GeminiVisionProvider(
            api_key=s.gemini_api_key, model=s.gemini_vision_model
        )
    if s.vision_provider == "bedrock":
        from backend.vision_provider.bedrock_vision import BedrockVisionProvider

        return BedrockVisionProvider(
            model_id=s.bedrock_vision_model, region=s.aws_region
        )
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
    if s.ocr_provider == "bedrock":
        from backend.ocr_provider.bedrock_ocr import BedrockOCRProvider

        return BedrockOCRProvider(model_id=s.bedrock_ocr_model, region=s.aws_region)
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
    if s.storage_provider == "s3":
        from backend.storage_provider.s3_storage import S3StorageProvider

        if not s.s3_bucket:
            raise ValueError("S3_BUCKET must be set when STORAGE_PROVIDER=s3")
        return S3StorageProvider(
            bucket=s.s3_bucket,
            region=s.aws_region,
            presign_expiry_seconds=s.s3_presign_expiry_seconds,
        )
    raise ValueError(f"Unknown STORAGE_PROVIDER: {s.storage_provider}")


# ──────────────────────────────────────────────────────────────
# QUEUE PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_queue():
    s = get_settings()
    if s.queue_provider == "memory":
        from backend.queue_provider.in_memory_queue import InMemoryQueueProvider

        return InMemoryQueueProvider()
    raise ValueError(f"Unknown QUEUE_PROVIDER: {s.queue_provider}")


# ──────────────────────────────────────────────────────────────
# SECRETS PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_secrets():
    s = get_settings()
    if s.secrets_provider == "env":
        from backend.secrets_provider.env_secrets import EnvSecretsProvider

        return EnvSecretsProvider()
    raise ValueError(f"Unknown SECRETS_PROVIDER: {s.secrets_provider}")


# ──────────────────────────────────────────────────────────────
# CHANNEL PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_channel():
    s = get_settings()
    if s.channel_provider == "webhook":
        from backend.channel_provider.webhook_channel import WebhookChannelProvider

        return WebhookChannelProvider()
    raise ValueError(f"Unknown CHANNEL_PROVIDER: {s.channel_provider}")