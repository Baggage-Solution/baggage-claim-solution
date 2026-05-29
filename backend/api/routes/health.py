from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Response

from backend.config import get_settings

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check(response: Response) -> Dict[str, Any]:
    """Return the application health status and active provider configuration.

    Returns HTTP 200 with status="ok" when all critical integrations are
    configured (GEMINI_API_KEY + SUPABASE_URL/KEY). Returns HTTP 503 with
    status="degraded" if any are missing — useful for liveness probes.

    Args:
        response: FastAPI Response object used to set HTTP status code.

    Returns:
        Dict with status, service name, env, provider names, and config flags.
    """
    settings = get_settings()

    gemini_configured = bool(settings.gemini_api_key)
    supabase_configured = bool(
        settings.supabase_url and settings.supabase_service_role_key
    )

    status = "ok" if (gemini_configured and supabase_configured) else "degraded"
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
            "gemini": gemini_configured,
            "supabase": supabase_configured,
        },
    }
