from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class WebhookResponse(BaseModel):
    session_id: str
    reply: str
    claim_id: Optional[str] = None
    routing_lane: Optional[int] = None
    voucher_code: Optional[str] = None
    conversation_step: str = "greeting"
    re_request_tag: bool = False
    re_request_damage: bool = False
    # True when conversation is over with no claim filed (no damage confirmed).
    # Frontend uses this to lock the input permanently.
    conversation_ended: bool = False

    # ── Echoed state fields ────────────────────────────────────────────────────
    # These are returned so the frontend can echo them back on the next request,
    # preserving A2/A3 results across turns (LangGraph does not persist them).

    # A2 results
    processed_damage_paths: List[str] = []
    damage_types: List[str] = []
    severity_score: float = 0.0
    brand_detected: Optional[str] = None
    is_luxury: bool = False
    compensation_estimate_usd: float = 0.0

    # A3 results
    flight_number: Optional[str] = None
    pnr: Optional[str] = None
    bag_id: Optional[str] = None
    ocr_confidence: float = 0.0

    error: Optional[str] = None