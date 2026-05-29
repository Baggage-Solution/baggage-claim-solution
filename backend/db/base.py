from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional  # ← add List


class DBProvider(ABC):
    """
    Abstract interface for claim persistence.
    Swap by changing DB_PROVIDER env var.
    """

    @abstractmethod
    async def save_claim(self, claim_data: Dict[str, Any]) -> str:
        """Persist a claim record. Returns claim_id."""
        raise NotImplementedError

    @abstractmethod
    async def get_claim(self, claim_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a claim by ID."""
        raise NotImplementedError

    @abstractmethod
    async def get_claims_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Return all claims matching the given status, newest first.
        Used by GET /claims/pending for the agent dashboard (T-017).

        Args:
            status: Status string e.g. 'AWAITING_REVIEW', 'RESOLVED', 'REJECTED'.

        Returns:
            List of claim dicts ordered by created_at descending.
        """
        raise NotImplementedError

    @abstractmethod
    async def update_claim_status(self, claim_id: str, status: str) -> None:
        """Update claim status (e.g. AWAITING_REVIEW → RESOLVED)."""
        raise NotImplementedError

    @abstractmethod
    async def update_claim(
        self, claim_id: str, fields: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update one or more columns of a claim in a single write and return the
        updated row.

        Used by the /decision endpoint so a staff approve/reject can persist the
        new status together with an edited compensation amount and a generated
        voucher code in one round-trip.

        Args:
            claim_id: Claim to update.
            fields: Mapping of column name → new value (e.g.
                    {"status": "RESOLVED", "compensation": 80.0,
                     "voucher_code": "VCH-ABCD1234"}).

        Returns:
            The updated claim dict, or None if the claim was not found.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_claim_count(self, pnr: str, days: int = 30) -> int:
        """Count claims for a PNR in the last N days (fraud frequency check)."""
        raise NotImplementedError

    @abstractmethod
    async def get_recent_hashes(self, pnr: str) -> list:
        """Return stored pHash values for a PNR (duplicate image fraud check)."""
        raise NotImplementedError