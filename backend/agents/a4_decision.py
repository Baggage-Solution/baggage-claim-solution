from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List

from backend.agents.base_agent import BaseAgent
from backend.config import get_settings
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)


def _generate_claim_id() -> str:
    """CLM-YYYYMMDD-XXXX format per architecture doc."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"{get_settings().claim_id_prefix}-{date_str}-{suffix}"


class A4DecisionAgent(BaseAgent):
    """
    Agent A4 — Decision Engine.

    Responsibilities:
    - Run fraud checks: pHash duplicate detection, claim frequency check.
    - Score severity and calculate final compensation.
    - Route to Lane 1 (auto-approve, ≤$100, no luxury, low fraud)
      or Lane 2 (staff review).
    - Generate claim_id and persist claim to DB.

    All 5 routing scenarios from architecture doc must pass in unit tests (T-012).
    """

    def __init__(self, db) -> None:
        super().__init__(
            name="a4_decision", description="Fraud check and routing decision engine"
        )
        self._db = db  # DBProvider instance

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        logger.info("a4_started", extra={"component": "A4"})
        settings = get_settings()

        try:
            state.claim_id = _generate_claim_id()

            # ── Fraud checks ──────────────────────────────────────────────
            # TODO (T-012):
            # 1. pHash duplicate check:
            #      import imagehash, PIL.Image
            #      hash = imagehash.phash(Image.open(path))
            #      existing_hashes = await self._db.get_recent_hashes(state.pnr)
            #      for h in existing_hashes:
            #          if abs(hash - h) < settings.fraud_phash_threshold:
            #              state.fraud_flags.append("phash_duplicate")
            # 2. Frequency check:
            #      count = await self._db.get_claim_count(state.pnr, days=settings.claim_frequency_window_days)
            #      if count >= settings.max_claims_per_passenger:
            #          state.fraud_flags.append("high_frequency")
            state.fraud_score = 0.0  # stub — replace with real score

            # ── Routing decision ──────────────────────────────────────────
            state.final_compensation_usd = state.compensation_estimate_usd

            if state.is_lane1_eligible():
                state.routing_lane = 1
            else:
                state.routing_lane = 2

            # ── Persist to DB ─────────────────────────────────────────────
            # TODO (T-012 + T-014):
            # await self._db.save_claim(state)

            state.add_debug("a4_lane", state.routing_lane)
            state.add_debug("a4_fraud_flags", state.fraud_flags)

        except Exception as exc:
            logger.exception("a4_failed")
            state.set_error(f"A4 error: {exc}")

        logger.info(
            "a4_completed",
            extra={
                "component": "A4",
                "claim_id": state.claim_id,
                "lane": state.routing_lane,
            },
        )
        return state
