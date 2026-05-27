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
    # True when A2 found a clear photo with no damage. Echoed so the flag can
    # be re-evaluated each turn (a new, genuinely damaged photo clears it).
    no_damage_detected: Optional[bool] = False

    # Optional QR context (T-018) — accepted but not required.
    airport_context: Optional[str] = None
    terminal_context: Optional[str] = None

    # A2 results — echoed so confirm turn has correct damage data for A4
    processed_damage_paths: Optional[List[str]] = None
    damage_types: Optional[List[str]] = None
    severity_score: Optional[float] = None
    brand_detected: Optional[str] = None
    is_luxury: Optional[bool] = None
    compensation_estimate_usd: Optional[float] = None

    # A3 results — echoed so confirm turn has correct OCR data for A4
    # processed_tag_paths prevents A3 re-running OCR on an already-scanned tag.
    processed_tag_paths: Optional[List[str]] = None
    flight_number: Optional[str] = None
    pnr: Optional[str] = None
    bag_id: Optional[str] = None
    ocr_confidence: Optional[float] = None