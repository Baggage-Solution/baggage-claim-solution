from __future__ import annotations

from pydantic import BaseModel
from typing import Optional


class WebhookResponse(BaseModel):
    session_id: str
    reply: str                              # message to display in simulator
    claim_id: Optional[str] = None
    routing_lane: Optional[int] = None      # 1 or 2, set after A4 runs
    voucher_code: Optional[str] = None      # Lane 1 only
    conversation_step: str = "greeting"
    re_request_tag: bool = False
    re_request_damage: bool = False
    error: Optional[str] = None
