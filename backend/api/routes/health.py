from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Response

from backend.config import get_settings
from backend.dependencies import provide_db

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check(response: Response) -> Dict[str, Any]:
    """Return the application health status and active provider configuration.

    Returns HTTP 200 with status="ok" when all critical integrations are
    configured (LLM provider API key + a working DB provider). Returns
    HTTP 503 with status="degraded" if any are missing — useful for
    liveness probes.

    DB readiness is checked via provide_db() rather than reading
    provider-specific settings (e.g. supabase_url) directly — this keeps
    the check cloud/db-agnostic. provide_db() already returns None for
    any DB_PROVIDER backend that isn't fully configured, so this works
    unchanged whether DB_PROVIDER is supabase, postgres, or any future
    backend.

    Args:
        response: FastAPI Response object used to set HTTP status code.

    Returns:
        Dict with status, service name, env, provider names, and config flags.
    """
    settings = get_settings()

    llm_configured = bool(settings.gemini_api_key)
    db_configured = provide_db() is not None

    status = "ok" if (llm_configured and db_configured) else "degraded"
    if status == "degraded":
        response.status_code = 503

    return {
        "status": status,
        "service": settings.service_name,
        "env": settings.app_env,
        "providers": {
            "llm": settings.llm_provider,
            "vision": settings.vision_provider,
            "ocr": settings.ocr_provider,
            "db": settings.db_provider,
            "storage": settings.storage_provider,
        },
        "configured": {
            "llm": llm_configured,
            "db": db_configured,
        },
    }