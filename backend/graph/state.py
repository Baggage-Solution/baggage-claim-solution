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
    conversation_ended: bool = False

    # ── A2 — VISION ────────────────────────────────────────────────────────────
    processed_damage_paths: List[str] = field(default_factory=list)
    damage_types: List[str] = field(default_factory=list)
    severity_score: float = 0.0
    brand_detected: Optional[str] = None
    is_luxury: bool = False
    compensation_estimate_usd: float = 0.0
    # A2 looked clearly and the bag is undamaged (distinct from re_request_damage,
    # which means "too blurry, retake").
    no_damage_detected: bool = False

    # ── ISSUE #1 — NON-BAG / OBJECT GATE ─────────────────────────────────────────
    # Set True by A2 when the most recent NEW image(s) were not luggage at all
    # (e.g. a watch, a person). A1 then politely asks for a real bag photo
    # instead of pretending it analysed a bag.
    not_a_bag: bool = False
    last_object_description: Optional[str] = None
    # How many times in a row the passenger has uploaded a non-bag image.
    # After NON_BAG_ATTEMPT_LIMIT, A1 gently ends the conversation.
    non_bag_attempts: int = 0

    # ── ISSUE #2 / #4 — TAG FOUND INSIDE A DAMAGE PHOTO ───────────────────────────
    # Set True by A2 when a damage photo ALSO contained a legible bag tag, so A3
    # should run OCR on that same image (no separate tag upload needed).
    tag_in_damage_photo: bool = False
    # Damage-photo paths whose embedded tag is worth OCR-ing. A3 consumes these.
    tag_candidate_paths: List[str] = field(default_factory=list)

    # ── A3 — OCR ───────────────────────────────────────────────────────────────
    flight_number: Optional[str] = None
    pnr: Optional[str] = None
    bag_id: Optional[str] = None
    ocr_confidence: float = 0.0
    processed_tag_paths: List[str] = field(default_factory=list)
    # True once we have usable tag data from ANY source (OCR or manual entry).
    tag_data_complete: bool = False
    # True when tag data came from the passenger typing/entering it manually
    # rather than from OCR (issue #3). Affects fraud weighting in A4.
    tag_manually_entered: bool = False

    # ── ISSUE #3 — MANUAL TAG ENTRY ──────────────────────────────────────────────
    # Free-text or structured tag details supplied by the passenger when they
    # have no tag or OCR failed. Parsed by A3 into flight_number / pnr / bag_id.
    manual_tag_text: Optional[str] = None
    manual_flight_number: Optional[str] = None
    manual_pnr: Optional[str] = None
    manual_bag_id: Optional[str] = None
    # Set True by A1/A3 to signal the UI to offer the manual-entry form.
    offer_manual_entry: bool = False

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
        """Record an error message and mark execution as completed.

        Called by agents when an unrecoverable error occurs. Sets the
        error field for downstream logging and marks the graph run as done.

        Args:
            message: Human-readable error description.
        """
        self.error = message
        self.execution_completed = True

    def add_debug(self, key: str, value: Any) -> None:
        """Append a key/value pair to the debug dict for structured logging.

        Used by agents to surface intermediate values (e.g. confidence scores,
        image counts) without polluting the main state fields.

        Args:
            key: Debug field name (e.g. "a2_images_processed").
            value: Any JSON-serialisable value.
        """
        self.debug[key] = value

    def is_lane1_eligible(self) -> bool:
        """Determine whether this claim qualifies for Lane 1 auto-approval.

        Lane 1 requires ALL of:
          - Estimated compensation <= LANE1_MAX_COMPENSATION_USD (default $100).
          - Not a luxury brand bag.
          - Fraud score below 0.5.

        Returns:
            bool: True if the claim can be auto-approved; False routes to Lane 2.
        """
        from backend.config import get_settings

        s = get_settings()
        return (
            self.compensation_estimate_usd <= s.lane1_max_compensation_usd
            and not self.is_luxury
            and self.fraud_score < 0.5
        )
