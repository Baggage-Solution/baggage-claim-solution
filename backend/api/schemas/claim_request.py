from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class WebhookRequest(BaseModel):
    """Inbound payload from the React simulator on every passenger turn.

    The frontend echoes back all agent-computed fields from the previous
    response (A2 results, A3 results, conversation_step, etc.) so that
    each webhook call is stateless on the backend — the full ClaimState
    is reconstructed from these fields on every request.
    """

    session_id: str
    message: str
    image_paths: Optional[List[str]] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None

    # ── Echoed state fields ────────────────────────────────────────────────────
    conversation_step: Optional[str] = "greeting"
    conversation_ended: Optional[bool] = False
    no_damage_detected: Optional[bool] = False

    # Issue #1 — object gate (non-bag detection)
    not_a_bag: Optional[bool] = False
    last_object_description: Optional[str] = None
    non_bag_attempts: Optional[int] = 0

    # Issue #2/#4 — tag spotted inside a damage photo
    tag_in_damage_photo: Optional[bool] = False
    tag_candidate_paths: Optional[List[str]] = None

    # Optional QR context (T-018)
    airport_context: Optional[str] = None
    terminal_context: Optional[str] = None

    # A2 results
    processed_damage_paths: Optional[List[str]] = None
    damage_types: Optional[List[str]] = None
    severity_score: Optional[float] = None
    brand_detected: Optional[str] = None
    is_luxury: Optional[bool] = None
    compensation_estimate_usd: Optional[float] = None

    # A3 results
    processed_tag_paths: Optional[List[str]] = None
    flight_number: Optional[str] = None
    pnr: Optional[str] = None
    bag_id: Optional[str] = None
    ocr_confidence: Optional[float] = None
    tag_data_complete: Optional[bool] = False
    tag_manually_entered: Optional[bool] = False

    # Issue #3 — manual tag entry (passenger-supplied)
    manual_tag_text: Optional[str] = None
    manual_flight_number: Optional[str] = None
    manual_pnr: Optional[str] = None
    manual_bag_id: Optional[str] = None
    offer_manual_entry: Optional[bool] = False
