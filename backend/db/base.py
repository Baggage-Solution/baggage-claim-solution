from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class DBProvider(ABC):
    """
    Abstract interface for claim persistence.
    Swap by changing DB_PROVIDER env var.
    Future: implement PostgresDBProvider for any PostgreSQL backend.
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
    async def update_claim_status(self, claim_id: str, status: str) -> None:
        """Update claim status (e.g. AWAITING_REVIEW → RESOLVED)."""
        raise NotImplementedError

    @abstractmethod
    async def get_claim_count(self, pnr: str, days: int = 30) -> int:
        """Count claims for a PNR in the last N days (fraud frequency check)."""
        raise NotImplementedError

    @abstractmethod
    async def get_recent_hashes(self, pnr: str) -> list:
        """Return stored pHash values for a PNR (duplicate image fraud check)."""
        raise NotImplementedError
