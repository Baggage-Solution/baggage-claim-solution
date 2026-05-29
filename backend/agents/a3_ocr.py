from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from backend.agents.base_agent import BaseAgent
from backend.graph.state import ClaimState

logger = logging.getLogger(__name__)

PNR_PATTERN = re.compile(r"^[A-Z0-9]{6}$")
BAG_ID_PATTERN = re.compile(r"^\d{10,12}$")
# Flight number: 2-letter/alphanumeric airline code + 1-4 digits (e.g. AI202, 6E531).
FLIGHT_PATTERN = re.compile(r"^[A-Z0-9]{2}\d{1,4}$")

OCR_CONFIDENCE_THRESHOLD = 0.7


class A3OCRAgent(BaseAgent):
    """
    Agent A3 — OCR / Data Extraction.

    Sources of tag data, in priority order:
      1. Manual entry from the passenger (free-text or structured form) — issue #3.
         If present, it's authoritative and no OCR call is made.
      2. A dedicated bag-tag photo (filename "tag_*").
      3. A tag spotted INSIDE a damage photo by A2 (tag_candidate_paths) — #2/#4.

    Dedup guards (processed_tag_paths) prevent re-OCR of an image already scanned.
    """

    def __init__(self, ocr) -> None:
        super().__init__(name="a3_ocr", description="Bag tag OCR extraction agent")
        self._ocr = ocr

    # ── Manual entry parsing (issue #3) ──────────────────────────────────────────
    def _normalize_flight(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        cleaned = re.sub(r"\s+", "", str(value)).upper()
        return cleaned if FLIGHT_PATTERN.match(cleaned) else None

    def _normalize_pnr(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        cleaned = str(value).strip().upper()
        return cleaned if PNR_PATTERN.match(cleaned) else None

    def _normalize_bag_id(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        cleaned = str(value).strip().replace(" ", "")
        return cleaned if BAG_ID_PATTERN.match(cleaned) else None

    def _parse_free_text(
        self, text: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Best-effort extraction of flight / PNR / bag id from a natural-language
        message like "flight AI202, PNR is ABC123, bag 0123456789".

        Strategy: try labelled patterns first ("flight: X", "pnr X"), then fall
        back to scanning loose tokens against the format regexes.
        """
        if not text:
            return None, None, None
        upper = text.upper()

        flight = pnr = bag_id = None

        # Labelled forms.
        m = re.search(r"FLIGHT\s*(?:NO|NUMBER|#|:|=)?\s*([A-Z0-9]{2}\s?\d{1,4})", upper)
        if m:
            flight = self._normalize_flight(m.group(1))
        m = re.search(r"PNR\s*(?:NO|NUMBER|#|:|=|IS)?\s*([A-Z0-9]{6})", upper)
        if m:
            pnr = self._normalize_pnr(m.group(1))
        m = re.search(r"BAG\s*(?:TAG|ID|NO|NUMBER|#|:|=)?\s*(\d[\d\s]{8,14}\d)", upper)
        if m:
            bag_id = self._normalize_bag_id(m.group(1))

        # Fallback: scan loose tokens for anything matching a format we still need.
        if not (flight and pnr and bag_id):
            tokens = re.split(r"[\s,;]+", upper)
            for tok in tokens:
                t = tok.strip().strip(".:#")
                if not flight and FLIGHT_PATTERN.match(t):
                    flight = t
                elif not bag_id and BAG_ID_PATTERN.match(t.replace(" ", "")):
                    bag_id = t.replace(" ", "")
                elif not pnr and PNR_PATTERN.match(t) and not t.isdigit():
                    # PNR must not be purely numeric (avoids catching short numbers).
                    pnr = t

        return flight, pnr, bag_id

    def _apply_manual_entry(self, state: ClaimState) -> bool:
        """
        Populate tag fields from manual entry if the passenger supplied any.
        Returns True if usable manual data was found.
        """
        # Structured fields take priority over free text.
        flight = self._normalize_flight(state.manual_flight_number)
        pnr = self._normalize_pnr(state.manual_pnr)
        bag_id = self._normalize_bag_id(state.manual_bag_id)

        if not (flight or pnr or bag_id) and state.manual_tag_text:
            flight, pnr, bag_id = self._parse_free_text(state.manual_tag_text)

        if not (flight or pnr or bag_id):
            return False

        # Merge onto any existing values (don't wipe good OCR data with blanks).
        state.flight_number = flight or state.flight_number
        state.pnr = pnr or state.pnr
        state.bag_id = bag_id or state.bag_id
        state.tag_manually_entered = True
        state.ocr_confidence = max(state.ocr_confidence, 1.0)  # user-asserted
        state.re_request_tag = False
        state.offer_manual_entry = False
        logger.info(
            "a3_manual_entry_applied",
            extra={
                "flight_number": bool(state.flight_number),
                "pnr": bool(state.pnr),
                "bag_id": bool(state.bag_id),
            },
        )
        return True

    def _tag_is_usable(self, state: ClaimState) -> bool:
        # We consider tag data usable if we have at least a flight number or bag id.
        return bool(state.flight_number or state.bag_id)

    async def handle(self, state: ClaimState, tasks: List[str]) -> ClaimState:
        """Run OCR extraction on all available bag tag sources.

        Processes tag data in priority order: (1) manual entry if present,
        (2) dedicated tag photos (filename contains "tag"), (3) tag candidates
        from damage photos identified by A2. Writes flight_number, pnr, bag_id,
        and ocr_confidence to state.

        Args:
            state: The shared ClaimState from the LangGraph pipeline.
            tasks: Unused — present for BaseAgent interface compliance.

        Returns:
            ClaimState: Updated state with OCR results and tag_data_complete flag.
        """
        logger.info("a3_started", extra={"component": "A3"})

        try:
            # ── Source 1: manual entry (issue #3) — authoritative, no OCR call ─
            if (
                state.manual_tag_text
                or state.manual_flight_number
                or state.manual_pnr
                or state.manual_bag_id
            ):
                if self._apply_manual_entry(state):
                    state.tag_data_complete = self._tag_is_usable(state)
                    logger.info(
                        "a3_completed",
                        extra={
                            "component": "A3",
                            "source": "manual",
                            "pnr": state.pnr,
                            "flight_number": state.flight_number,
                            "bag_id": state.bag_id,
                            "tag_data_complete": state.tag_data_complete,
                        },
                    )
                    return state

            # ── Build the OCR candidate list ──────────────────────────────────
            # Dedicated tag photos (filename "tag_*") + tags A2 spotted inside
            # damage photos (issue #2/#4), minus anything already OCR'd.
            done = set(state.processed_tag_paths)
            dedicated_tags = [p for p in state.image_paths if "tag" in p.lower()]
            embedded_tags = list(state.tag_candidate_paths)

            # Preserve order, de-dupe, drop already-processed.
            ordered: List[str] = []
            for p in dedicated_tags + embedded_tags:
                if p not in done and p not in ordered:
                    ordered.append(p)

            if not ordered:
                # Nothing new to OCR. Keep any existing data as-is.
                state.tag_data_complete = self._tag_is_usable(state)
                logger.info(
                    "a3_skipped",
                    extra={
                        "reason": "no_new_tag_sources",
                        "have_data": state.tag_data_complete,
                    },
                )
                return state

            state.re_request_tag = False

            # ── OCR each new candidate until we get usable data ───────────────
            best_conf = state.ocr_confidence
            for target in ordered:
                result = await self._ocr.extract_bag_tag(target)
                state.processed_tag_paths = list(
                    set(state.processed_tag_paths) | {target}
                )
                best_conf = max(best_conf, result.confidence)

                if result.confidence < OCR_CONFIDENCE_THRESHOLD:
                    logger.info(
                        "a3_low_confidence",
                        extra={
                            "image": target,
                            "confidence": result.confidence,
                            "threshold": OCR_CONFIDENCE_THRESHOLD,
                        },
                    )
                    continue  # try the next candidate, if any

                # Good read — merge fields (don't overwrite good values with None).
                state.flight_number = result.flight_number or state.flight_number
                state.pnr = result.pnr or state.pnr
                state.bag_id = result.bag_id or state.bag_id

                if not result.pnr:
                    logger.warning("a3_pnr_not_extracted", extra={"image": target})
                if not result.bag_id:
                    logger.warning("a3_bag_id_not_extracted", extra={"image": target})

                # Stop as soon as we have usable data — no need to OCR further
                # candidates (avoids extra Gemini calls and matches "first good
                # tag wins" behaviour).
                if self._tag_is_usable(state):
                    break

            state.ocr_confidence = best_conf
            state.add_debug("a3_confidence", best_conf)

            state.tag_data_complete = self._tag_is_usable(state)

            # If we still have no usable tag data, ask for a retake AND offer the
            # manual-entry fallback (issue #3).
            if not state.tag_data_complete:
                state.re_request_tag = True
                state.offer_manual_entry = True
                logger.info(
                    "a3_no_usable_tag",
                    extra={"best_conf": best_conf, "offer_manual_entry": True},
                )

        except Exception as exc:
            logger.exception("a3_failed")
            state.set_error(f"A3 error: {exc}")

        logger.info(
            "a3_completed",
            extra={
                "component": "A3",
                "pnr": state.pnr,
                "flight_number": state.flight_number,
                "bag_id": state.bag_id,
                "confidence": state.ocr_confidence,
                "tag_data_complete": state.tag_data_complete,
                "manual": state.tag_manually_entered,
            },
        )
        return state
