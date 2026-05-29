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
    conversation_ended: bool = False
    no_damage_detected: bool = False

    # Issue #1 — object gate
    not_a_bag: bool = False
    last_object_description: Optional[str] = None
    non_bag_attempts: int = 0

    # Issue #2/#4 — tag in damage photo
    tag_in_damage_photo: bool = False
    tag_candidate_paths: List[str] = []

    # A2 results
    processed_damage_paths: List[str] = []
    damage_types: List[str] = []
    severity_score: float = 0.0
    brand_detected: Optional[str] = None
    is_luxury: bool = False
    compensation_estimate_usd: float = 0.0

    # A3 results
    processed_tag_paths: List[str] = []
    flight_number: Optional[str] = None
    pnr: Optional[str] = None
    bag_id: Optional[str] = None
    ocr_confidence: float = 0.0
    tag_data_complete: bool = False
    tag_manually_entered: bool = False

    # Issue #3 — manual tag entry
    offer_manual_entry: bool = False

    error: Optional[str] = None