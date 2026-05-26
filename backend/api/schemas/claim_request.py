from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class WebhookRequest(BaseModel):
    session_id: str
    message: str
    image_paths: Optional[List[str]] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None

    # ── Echoed state fields ────────────────────────────────────────────────────
    # LangGraph MemorySaver does NOT persist plain dataclass fields between
    # separate ainvoke() calls. The frontend echoes these values from the last
    # response back on every request so the backend always has the full picture.
    # Pattern: backend sets → response carries → frontend stores → frontend echoes.

    conversation_step: Optional[str] = "greeting"
    conversation_ended: Optional[bool] = False

    # A2 results — echoed so confirm turn has correct damage data for A4
    processed_damage_paths: Optional[List[str]] = None
    damage_types: Optional[List[str]] = None
    severity_score: Optional[float] = None
    brand_detected: Optional[str] = None
    is_luxury: Optional[bool] = None
    compensation_estimate_usd: Optional[float] = None

    # A3 results — echoed so confirm turn has correct OCR data for A4
    flight_number: Optional[str] = None
    pnr: Optional[str] = None
    bag_id: Optional[str] = None
    ocr_confidence: Optional[float] = None