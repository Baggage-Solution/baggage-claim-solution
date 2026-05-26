from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ClaimState:
    """
    Shared state object flowing across all 5 LangGraph agent nodes.
    Adapted from Proj A LangGraphState — same pattern, claim-domain fields.

    Flow:
        Webhook → A1 (conversation) → A2 (vision) → A3 (ocr) → A4 (decision) → A5 (notify)
    """

    # ──────────────────────────────────────────────────────────
    # INPUT  (set by webhook, persists through all nodes)
    # ──────────────────────────────────────────────────────────
    session_id: str = ""
    passenger_message: str = ""
    image_paths: List[str] = field(default_factory=list)   # local paths after upload
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)

    # ──────────────────────────────────────────────────────────
    # TRACEABILITY
    # ──────────────────────────────────────────────────────────
    request_id: Optional[str] = None
    claim_id: Optional[str] = None     # set by A4 — format: CLM-YYYYMMDD-XXXX

    # ──────────────────────────────────────────────────────────
    # A1 — CONVERSATION AGENT OUTPUT
    # ──────────────────────────────────────────────────────────
    conversation_step: str = "greeting"   # greeting | damage_photos | tag_photo | confirm | result
    a1_response: Optional[str] = None     # message to send back to passenger
    re_request_tag: bool = False          # True when A3 asks passenger to retake tag photo
    re_request_damage: bool = False       # True when A2 asks for better damage photos

    # ──────────────────────────────────────────────────────────
    # A2 — VISION ANALYSIS AGENT OUTPUT
    # ──────────────────────────────────────────────────────────
    damage_types: List[str] = field(default_factory=list)      # e.g. ["cracked shell", "broken wheel"]
    severity_score: float = 0.0                                 # 0.0–1.0
    brand_detected: Optional[str] = None                        # e.g. "Samsonite" or None
    is_luxury: bool = False
    compensation_estimate_usd: float = 0.0

    # ──────────────────────────────────────────────────────────
    # A3 — OCR / DATA EXTRACTION AGENT OUTPUT
    # ──────────────────────────────────────────────────────────
    flight_number: Optional[str] = None
    pnr: Optional[str] = None
    bag_id: Optional[str] = None
    ocr_confidence: float = 0.0   # 0.0–1.0; below 0.7 triggers re_request_tag

    # ──────────────────────────────────────────────────────────
    # A4 — DECISION ENGINE OUTPUT
    # ──────────────────────────────────────────────────────────
    routing_lane: Optional[int] = None      # 1 = auto-approve, 2 = staff review
    fraud_score: float = 0.0
    fraud_flags: List[str] = field(default_factory=list)   # e.g. ["phash_duplicate"]
    final_compensation_usd: float = 0.0

    # ──────────────────────────────────────────────────────────
    # A5 — NOTIFICATION AGENT OUTPUT
    # ──────────────────────────────────────────────────────────
    voucher_code: Optional[str] = None      # Lane 1: issued instantly
    notification_sent: bool = False
    hitl_queued: bool = False               # Lane 2: claim queued for staff review

    # ──────────────────────────────────────────────────────────
    # DEBUG / ERROR
    # ──────────────────────────────────────────────────────────
    debug: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    execution_completed: bool = False

    # ──────────────────────────────────────────────────────────
    # HELPERS  (same pattern as Proj A LangGraphState)
    # ──────────────────────────────────────────────────────────
    def set_error(self, message: str) -> None:
        self.error = message
        self.execution_completed = True

    def add_debug(self, key: str, value: Any) -> None:
        self.debug[key] = value

    def is_lane1_eligible(self) -> bool:
        """True when damage qualifies for instant auto-approval."""
        from backend.config import get_settings
        s = get_settings()
        return (
            self.compensation_estimate_usd <= s.lane1_max_compensation_usd
            and not self.is_luxury
            and self.fraud_score < 0.5
        )
