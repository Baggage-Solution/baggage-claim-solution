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

    # ── A3 — OCR ───────────────────────────────────────────────────────────────
    flight_number: Optional[str] = None
    pnr: Optional[str] = None
    bag_id: Optional[str] = None
    ocr_confidence: float = 0.0

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
