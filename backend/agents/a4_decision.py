from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend.agents.base_agent import BaseAgent
from backend.config import get_settings
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

# Minimum severity score for a claim to be accepted.
# Below this threshold the passenger is told no significant damage was detected.
_MIN_DAMAGE_SEVERITY = 0.1


def _generate_claim_id() -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"{get_settings().claim_id_prefix}-{date_str}-{suffix}"


def _state_to_claim_dict(state: ClaimState) -> Dict[str, Any]:
    return {
        "id": state.claim_id,
        "pnr": state.pnr,
        "bag_id": state.bag_id,
        "flight_number": state.flight_number,
        "damage_types": state.damage_types,
        "severity_score": state.severity_score,
        "is_luxury": state.is_luxury,
        "brand": state.brand_detected,
        "compensation": state.final_compensation_usd,
        "fraud_score": state.fraud_score,
        "fraud_flags": state.fraud_flags,
        "routing_lane": state.routing_lane,
        "voucher_code": state.voucher_code,
        "status": "PENDING",
    }


class A4DecisionAgent(BaseAgent):
    """
    Agent A4 — Decision Engine.

    Responsibilities:
    - Guard against no-damage claims (severity below threshold → reject).
    - Run fraud checks: pHash duplicate detection, claim frequency check.
    - Score severity and calculate final compensation.
    - Route to Lane 1 (auto-approve: <=100 USD, no luxury, low fraud)
      or Lane 2 (staff review).
    - Generate claim_id and persist claim to DB.

    Provider: DBProvider (injected — never import Supabase directly here).
    Thresholds: all configurable via .env — see config.py.

    BUG FIX: save_claim() is now wrapped in its own try/except so a network
    error (e.g. [Errno 11001] getaddrinfo failed when Supabase is not
    reachable) no longer aborts the entire claim. The claim is processed
    in-memory and the routing decision is returned to the passenger even
    when DB persistence fails. The error is logged as a warning, not raised.
    """

    def __init__(self, db) -> None:
        super().__init__(
            name="a4_decision",
            description="Fraud check and routing decision engine",
        )
        self._db = db

    async def _run_phash_check(self, state: ClaimState) -> None:
        settings = get_settings()

        if not settings.imagehash_enabled:
            logger.debug("phash_check_disabled")
            return

        damage_paths = [
            p for p in state.image_paths if "tag" not in Path(p).name.lower()
        ]

        if not damage_paths:
            logger.debug("phash_check_skipped — no damage images")
            return

        if self._db is None:
            logger.warning(
                "phash_check_skipped — DB not configured (no Supabase credentials)"
            )
            return

        try:
            import imagehash
            from PIL import Image

            existing_hashes = await self._db.get_recent_hashes(state.pnr or "")

            for image_path in damage_paths:
                path = Path(image_path)
                if not path.exists():
                    logger.warning("phash_image_not_found", extra={"path": image_path})
                    continue

                current_hash = imagehash.phash(Image.open(path))

                for stored_hash_str in existing_hashes:
                    try:
                        stored_hash = imagehash.hex_to_hash(stored_hash_str)
                        distance = abs(current_hash - stored_hash)

                        if distance < settings.fraud_phash_threshold:
                            if "phash_duplicate" not in state.fraud_flags:
                                state.fraud_flags.append("phash_duplicate")
                                state.fraud_score = min(state.fraud_score + 0.4, 1.0)
                                logger.warning(
                                    "phash_duplicate_detected",
                                    extra={
                                        "pnr": state.pnr,
                                        "distance": distance,
                                        "image": image_path,
                                    },
                                )
                            break
                    except Exception:
                        continue

        except ImportError:
            logger.warning("imagehash_not_installed — skipping pHash check")
        except Exception as exc:
            logger.warning("phash_check_error — skipping", extra={"error": str(exc)})

    async def _run_frequency_check(self, state: ClaimState) -> None:
        settings = get_settings()

        if not state.pnr:
            logger.debug("frequency_check_skipped — no PNR in state")
            return

        if self._db is None:
            logger.warning(
                "frequency_check_skipped — DB not configured (no Supabase credentials)"
            )
            return

        try:
            count = await self._db.get_claim_count(
                state.pnr,
                days=settings.claim_frequency_window_days,
            )

            logger.info(
                "frequency_check_result",
                extra={
                    "pnr": state.pnr,
                    "count": count,
                    "threshold": settings.max_claims_per_passenger,
                },
            )

            if count >= settings.max_claims_per_passenger:
                if "high_frequency" not in state.fraud_flags:
                    state.fraud_flags.append("high_frequency")
                    state.fraud_score = min(state.fraud_score + 0.3, 1.0)
                    logger.warning(
                        "high_frequency_claim_detected",
                        extra={"pnr": state.pnr, "count": count},
                    )

        except Exception as exc:
            logger.warning(
                "frequency_check_error — skipping",
                extra={"error": str(exc)},
            )

    async def _persist_claim(self, state: ClaimState) -> None:
        """
        Persist the claim to the database.

        BUG FIX: previously this was an inline await inside the main try/except
        of handle(). Any network error (e.g. [Errno 11001] getaddrinfo failed
        when Supabase credentials are wrong or the host is unreachable) would
        propagate up, set state.error, and show "A4 error: ..." in the chat —
        even though the routing decision had already been made successfully.

        Now isolated in its own method with its own try/except. A DB failure
        logs a warning and leaves the claim processed in memory. The routing
        lane and compensation are already set at this point, so the passenger
        still gets their result (Lane 1 voucher or Lane 2 review message).

        Args:
            state: ClaimState with claim_id, routing_lane, and all fields set.
        """
        if self._db is None:
            logger.warning(
                "a4_db_save_skipped — DB not configured; claim processed "
                "in memory only. Set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY "
                "in .env to enable persistence.",
                extra={"claim_id": state.claim_id},
            )
            return

        try:
            claim_dict = _state_to_claim_dict(state)
            await self._db.save_claim(claim_dict)
            logger.info(
                "a4_db_save_ok",
                extra={"claim_id": state.claim_id, "lane": state.routing_lane},
            )
        except Exception as exc:
            # DB is unreachable or misconfigured — log it but do NOT fail the
            # claim. The passenger has already been routed; persisting to DB is
            # a best-effort side-effect in the POC, not a hard requirement.
            logger.warning(
                "a4_db_save_failed — claim processed in memory only",
                extra={
                    "claim_id": state.claim_id,
                    "error": str(exc),
                    "hint": (
                        "Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env. "
                        "If running without Supabase, this warning is expected."
                    ),
                },
            )

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        """Run fraud checks, routing decision, and claim persistence.

        Steps: guard against incomplete/no-damage claims → pHash duplicate
        detection → claim frequency check → final compensation calculation →
        Lane 1 or Lane 2 routing → persist claim to database.

        Args:
            state: The shared ClaimState from the LangGraph pipeline.
            tasks: Unused — present for BaseAgent interface compliance.

        Returns:
            ClaimState: Updated state with claim_id, routing_lane, fraud_score,
                and final_compensation_usd.
        """
        logger.info(
            "a4_started",
            extra={
                "component": "A4",
                "session_id": state.session_id,
                "severity_score": state.severity_score,
                "compensation_estimate": state.compensation_estimate_usd,
                "is_luxury": state.is_luxury,
                "damage_types": state.damage_types,
            },
        )

        # ── Guard 1: both the damage side and the tag side must be present ─────
        damage_images = [p for p in state.image_paths if "tag" not in p.lower()]
        tag_images = [p for p in state.image_paths if "tag" in p.lower()]
        have_tag_data = bool(
            tag_images or state.tag_data_complete or state.flight_number or state.bag_id
        )

        if state.image_paths and (not damage_images or not have_tag_data):
            logger.info(
                "a4_skipped",
                extra={
                    "reason": "incomplete_images",
                    "damage_count": len(damage_images),
                    "tag_count": len(tag_images),
                    "have_tag_data": have_tag_data,
                    "session_id": state.session_id,
                },
            )
            return state

        # ── Guard 2: skip if A2 or A3 flagged image quality issues ────────────
        if state.re_request_tag or state.re_request_damage:
            logger.info(
                "a4_skipped",
                extra={
                    "reason": "image_quality_retry_requested",
                    "re_request_tag": state.re_request_tag,
                    "re_request_damage": state.re_request_damage,
                    "session_id": state.session_id,
                },
            )
            return state

        # ── Guard 3: no damage detected — reject the claim ─────────────────────
        if (
            state.image_paths
            and state.severity_score < _MIN_DAMAGE_SEVERITY
            and not state.damage_types
        ):
            logger.warning(
                "a4_no_damage_detected",
                extra={
                    "session_id": state.session_id,
                    "damage_types": state.damage_types,
                    "severity_score": state.severity_score,
                },
            )
            state.conversation_ended = True
            state.set_error(
                "no_damage_detected: Our system did not detect significant damage "
                "on the submitted photos. If your bag is damaged, please retake "
                "clearer photos showing the affected areas."
            )
            return state

        try:
            # Step 1 — Generate claim ID
            state.claim_id = _generate_claim_id()

            # Step 2 — Fraud Check 1: pHash duplicate detection
            await self._run_phash_check(state)

            # Step 3 — Fraud Check 2: claim frequency
            await self._run_frequency_check(state)

            # Step 4 — Calculate final compensation
            if state.is_luxury:
                state.final_compensation_usd = state.compensation_estimate_usd * 1.5
            else:
                state.final_compensation_usd = state.compensation_estimate_usd

            # Step 5 — Routing decision
            if state.is_lane1_eligible():
                state.routing_lane = 1
            else:
                state.routing_lane = 2

            # Step 6 — Persist to DB (best-effort; never fails the claim)
            await self._persist_claim(state)

            # Step 7 — Debug logging
            state.add_debug("a4_lane", state.routing_lane)
            state.add_debug("a4_fraud_flags", state.fraud_flags)
            state.add_debug("a4_fraud_score", state.fraud_score)
            state.add_debug("a4_final_compensation", state.final_compensation_usd)

        except Exception as exc:
            logger.exception("a4_failed")
            state.set_error(f"A4 error: {exc}")

        logger.info(
            "a4_completed",
            extra={
                "component": "A4",
                "claim_id": state.claim_id,
                "lane": state.routing_lane,
                "fraud_score": state.fraud_score,
                "fraud_flags": state.fraud_flags,
                "final_compensation": state.final_compensation_usd,
            },
        )

        return state
