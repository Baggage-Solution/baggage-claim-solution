from __future__ import annotations

from abc import ABC, abstractmethod


class StorageProvider(ABC):
    """
    Abstract interface for photo upload storage.
    Swap by changing STORAGE_PROVIDER env var.
    Future: implement R2StorageProvider (Cloudflare R2 — free up to 10GB).
    """

    @abstractmethod
    async def save(self, file_bytes: bytes, filename: str, claim_id: str) -> str:
        """Persist uploaded photo. Returns storage path/URL."""
        raise NotImplementedError

    @abstractmethod
    async def get_path(self, filename: str, claim_id: str) -> str:
        """Return the local path or URL for a stored file."""
        raise NotImplementedError
