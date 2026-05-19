from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class WebhookRequest(BaseModel):
    session_id: str
    message: str
    image_paths: Optional[List[str]] = None  # paths returned by /upload
    conversation_history: Optional[List[Dict[str, Any]]] = None
