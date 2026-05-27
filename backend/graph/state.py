from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ClaimState:
    """
    Shared state object flowing across all 5 LangGraph agent nodes.

    Flow:
        Webhook → A1 (conversation) → A2 (vision) → A3 (ocr) → A4 (decision) → A5 (notify)
    """

    # ── INPUT ──────────────────────────────────────────────────────────────────
    session_id: str = ""
    passenger_message: str = ""
    image_paths: List[str] = field(default_factory=list)
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)

    # ── TRACEABILITY ───────────────────────────────────────────────────────────
    request_id: Optional[str] = None
    claim_id: Optional[str] = None

    # ── A1 — CONVERSATION ──────────────────────────────────────────────────────
    conversation_step: str = "greeting"
    a1_response: Optional[str] = None
    re_request_tag: bool = False
    re_request_damage: bool = False
    # Set True when the conversation has reached a terminal state with no claim:
    # - passenger confirmed no damage ("no damage sorry")
    # - A4 detected no damage in photos
    # Frontend uses this to lock the input so no further messages can be sent.
    conversation_ended: bool = False

    # ── A2 — VISION ────────────────────────────────────────────────────────────
    processed_damage_paths: List[str] = field(default_factory=list)
    damage_types: List[str] = field(default_factory=list)
    severity_score: float = 0.0
    brand_detected: Optional[str] = None
    is_luxury: bool = False
    compensation_estimate_usd: float = 0.0
    # Set True by A2 when damage photos were successfully analysed (good
    # confidence) but NO structural damage was found. This is distinct from
    # re_request_damage (which means "image too blurry, retake it").
    #
    # no_damage_detected = "we looked clearly and the bag is fine"
    # re_request_damage  = "we couldn't see clearly, send a better photo"
    #
    # A1 uses this flag to tell the passenger no damage was found and to NOT
    # advance the conversation to the tag-photo step. The flag is NON-terminal:
    # the passenger can still upload a different/clearer photo of real damage,
    # which clears the flag on the next A2 run. Only an explicit passenger
    # confirmation of "no damage" sets conversation_ended (terminal).
    no_damage_detected: bool = False

    # ── A3 — OCR ───────────────────────────────────────────────────────────────
    flight_number: Optional[str] = None
    pnr: Optional[str] = None
    bag_id: Optional[str] = None
    ocr_confidence: float = 0.0
    # Tag photos A3 has already run OCR on. Echoed back by the frontend each
    # turn (mirrors processed_damage_paths for A2). Prevents A3 from making a
    # redundant Gemini OCR call on the confirm turn, where the frontend resends
    # the already-scanned tag image along with the damage images.
    processed_tag_paths: List[str] = field(default_factory=list)

    # ── A4 — DECISION ──────────────────────────────────────────────────────────
    routing_lane: Optional[int] = None
    fraud_score: float = 0.0
    fraud_flags: List[str] = field(default_factory=list)
    final_compensation_usd: float = 0.0

    # ── A5 — NOTIFICATION ──────────────────────────────────────────────────────
    voucher_code: Optional[str] = None
    notification_sent: bool = False
    hitl_queued: bool = False

    # ── DEBUG / ERROR ──────────────────────────────────────────────────────────
    debug: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    execution_completed: bool = False

    def set_error(self, message: str) -> None:
        self.error = message
        self.execution_completed = True

    def add_debug(self, key: str, value: Any) -> None:
        self.debug[key] = value

    def is_lane1_eligible(self) -> bool:
        from backend.config import get_settings

        s = get_settings()
        return (
            self.compensation_estimate_usd <= s.lane1_max_compensation_usd
            and not self.is_luxury
            and self.fraud_score < 0.5
        )