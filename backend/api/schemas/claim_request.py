from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class WebhookRequest(BaseModel):
    session_id: str
    message: str
    image_paths: Optional[List[str]] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None
    # Frontend tracks and echoes back the step it received from the last response.
    # This is the authoritative conversation_step for the backend because
    # LangGraph's MemorySaver does NOT persist dataclass state between separate
    # ainvoke() calls — each call starts from the ClaimState defaults (step="greeting").
    # By having the frontend send the current step, the backend always knows
    # where in the conversation flow it is without needing a separate session store.
    conversation_step: Optional[str] = "greeting"
