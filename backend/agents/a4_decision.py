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


def _generate_claim_id() -> str:
    """
    Generate a unique claim ID in CLM-YYYYMMDD-XXXX format.

    Returns:
        Claim ID string e.g. 'CLM-20260520-A2E2'
    """
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"{get_settings().claim_id_prefix}-{date_str}-{suffix}"


def _state_to_claim_dict(state: ClaimState) -> Dict[str, Any]:
    """
    Convert ClaimState to a flat dict for DB persistence.

    Args:
        state: Current ClaimState after A4 processing.

    Returns:
        Dict matching the Supabase claims table schema.
    """
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
    - Run fraud checks: pHash duplicate detection, claim frequency check.
    - Score severity and calculate final compensation.
    - Route to Lane 1 (auto-approve: <=100 USD, no luxury, low fraud)
      or Lane 2 (staff review).
    - Generate claim_id and persist claim to DB.

    All 5 routing scenarios from architecture doc pass in unit tests (T-012).

    Provider: DBProvider (injected — never import Supabase directly here).
    Thresholds: all configurable via .env — see config.py.
    """

    def __init__(self, db) -> None:
        """
        Initialise A4 decision agent.

        Args:
            db: DBProvider instance (injected from dependencies.py).
        """
        super().__init__(
            name="a4_decision",
            description="Fraud check and routing decision engine",
        )
        self._db = db

    async def _run_phash_check(self, state: ClaimState) -> None:
        """
        Fraud Check 1 — Perceptual hash duplicate detection.

        Computes pHash for each damage photo and compares against hashes
        stored in DB for the same PNR. If hamming distance is below threshold,
        flags as duplicate submission.

        Args:
            state: Current ClaimState. Modifies fraud_score and fraud_flags in place.
        """
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
        """
        Fraud Check 2 — Claim frequency check.

        Counts claims filed for this PNR in the last N days.
        If count >= MAX_CLAIMS_PER_PASSENGER, flags as high frequency.

        Args:
            state: Current ClaimState. Modifies fraud_score and fraud_flags in place.
        """
        settings = get_settings()

        if not state.pnr:
            logger.debug("frequency_check_skipped — no PNR in state")
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

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        """
        Run fraud checks, make routing decision, generate claim ID, persist to DB.

        Args:
            state: Current ClaimState flowing through LangGraph pipeline.
            tasks: Unused — kept for BaseAgent interface compatibility.

        Returns:
            Updated ClaimState with claim_id, routing_lane, fraud_score, fraud_flags.
        """
        logger.info(
            "a4_started",
            extra={
                "component": "A4",
                "session_id": state.session_id,
                "severity_score": state.severity_score,
                "compensation_estimate": state.compensation_estimate_usd,
                "is_luxury": state.is_luxury,
            },
        )

        # ── Guard: only run if both damage AND tag images have been uploaded ────
        # The orchestrator's conditional edge should prevent A4 from being called
        # on text-only turns, but this guard is a belt-and-suspenders safety net.
        # Without it, a blank-state A4 run would set routing_lane on every turn
        # and cause A1._advance_step() to jump straight to "result".
        damage_images = [p for p in state.image_paths if "tag" not in p.lower()]
        tag_images = [p for p in state.image_paths if "tag" in p.lower()]

        # Guard: only skip when images are present but the set is incomplete.
        # An empty image_paths means A4 is being called directly (unit tests,
        # or confirm step where orchestrator already validated both types exist).
        # In that case, fall through and let A4 run on the state it has.
        if state.image_paths and (not damage_images or not tag_images):
            logger.info(
                "a4_skipped",
                extra={
                    "reason": "incomplete_images",
                    "damage_count": len(damage_images),
                    "tag_count": len(tag_images),
                    "session_id": state.session_id,
                },
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

            # Step 5 — Routing decision via is_lane1_eligible()
            if state.is_lane1_eligible():
                state.routing_lane = 1
            else:
                state.routing_lane = 2

            # Step 6 — Persist to DB
            claim_dict = _state_to_claim_dict(state)
            await self._db.save_claim(claim_dict)

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
            },
        )

        return state
