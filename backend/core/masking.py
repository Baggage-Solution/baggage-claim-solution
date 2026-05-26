from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel


MASK_TOKEN = "[REDACTED]"

# ── Proj A patterns (kept as-is) ─────────────────────────────────────────────
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\-\s().]{7,}\d)(?!\w)")
PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE)
LABELED_ACCOUNT_RE = re.compile(
    r"(?i)\b(?:(?:bank\s+)?acc(?:ount)?(?:\s*(?:number|no|#))?|pan(?:\s*(?:number|no|#|acc(?:ount)?))?|ifsc(?:\s*(?:code))?)"
    r"(\s*[:=\-]?\s*)([A-Z0-9]{4,18})\b"
)
EMPLOYEE_CODE_RE = re.compile(
    r"\bemp(?:loyee)?[-_ ]?(?:id|code)?[-_ ]?\d{3,}\b",
    re.IGNORECASE,
)

# ── Proj B extensions ─────────────────────────────────────────────────────────
# PNR: 6-char alphanumeric booking reference
PNR_RE = re.compile(r"\b[A-Z0-9]{6}\b")

# Airline bag ID: 10-digit IATA numeric bag tag
BAG_ID_RE = re.compile(r"\b\d{10}\b")

# Flight number: e.g. AI-202, 6E 1234, EK504
FLIGHT_NUMBER_RE = re.compile(r"\b[A-Z]{1,2}[-\s]?\d{1,4}\b", re.IGNORECASE)

# Claim ID: CLM-YYYYMMDD-XXXX
CLAIM_ID_RE = re.compile(r"\bCLM-\d{8}-[A-Z0-9]{4}\b", re.IGNORECASE)


_PARTIAL_PII_KEYWORDS = (
    "pnr",
    "bag_id",
    "bagid",
    "flight",
    "passenger",
    "employee",
    "emp_id",
    "claim_id",
    "claimid",
    "ticket",
    "asset",
)


def mask_sensitive_text(text: str) -> str:
    """
    Apply PII masking to free-text strings.
    Used in log formatters to sanitise user-submitted messages before logging.
    """
    text = PAN_RE.sub(MASK_TOKEN, text)
    text = LABELED_ACCOUNT_RE.sub(r"\1" + MASK_TOKEN, text)
    text = EMPLOYEE_CODE_RE.sub(MASK_TOKEN, text)
    text = CLAIM_ID_RE.sub(MASK_TOKEN, text)
    # NOTE: PNR, bag ID, flight number are NOT globally masked in free text
    # because they appear in too many non-PII contexts (dates, codes, etc.)
    # They are only masked when appearing alongside explicit keyword labels — see below.
    return text


def mask_sensitive_value(key: str, value: Any) -> Any:
    """
    Mask a structured log field based on its key name.
    Called per-field in the JSON log formatter.
    """
    if not isinstance(value, str):
        return value

    key_lower = key.lower()
    if any(kw in key_lower for kw in _PARTIAL_PII_KEYWORDS):
        return MASK_TOKEN

    return mask_sensitive_text(value)
