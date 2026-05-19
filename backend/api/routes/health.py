from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Response

from backend.config import get_settings

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check(response: Response) -> Dict[str, Any]:
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
