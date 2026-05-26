from __future__ import annotations

from functools import lru_cache

from backend.config import get_settings

# ──────────────────────────────────────────────────────────────
# LLM PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_llm():
    s = get_settings()
    if s.llm_provider == "gemini":
        from backend.llm_provider.gemini_llm import GeminiLLMProvider
        return GeminiLLMProvider(api_key=s.gemini_api_key, model=s.gemini_model)
    raise ValueError(f"Unknown LLM_PROVIDER: {s.llm_provider}. Implement the provider and add it here.")


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
# DATABASE PROVIDER
# ──────────────────────────────────────────────────────────────
@lru_cache
def provide_db():
    s = get_settings()
    if s.db_provider == "supabase":
        from backend.db.supabase_client import SupabaseDBProvider
        return SupabaseDBProvider(url=s.supabase_url, service_role_key=s.supabase_service_role_key)
    raise ValueError(f"Unknown DB_PROVIDER: {s.db_provider}")


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
