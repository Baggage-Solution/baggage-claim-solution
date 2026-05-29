from __future__ import annotations

import logging
import os

from backend.storage_provider.base import StorageProvider

logger = logging.getLogger(__name__)


class LocalStorageProvider(StorageProvider):
    """
    Local disk storage (POC — zero cost).
    Saves uploads to LOCAL_STORAGE_BASE_PATH/claim_id/filename.
    Future swap: set STORAGE_PROVIDER=r2 → r2_storage.py (S3-compatible API).
    """

    def __init__(self, base_path: str = "./data/uploads") -> None:
        self._base = base_path

    async def save(self, file_bytes: bytes, filename: str, claim_id: str) -> str:
        """Save raw file bytes to disk under data/uploads/{claim_id}/{filename}.

        Creates the claim directory if it does not exist.

        Args:
            file_bytes: Raw bytes of the uploaded image.
            filename: Target filename (e.g. damage_001.jpg).
            claim_id: Claim or session identifier used as the subdirectory name.

        Returns:
            str: Absolute file path where the bytes were written.
        """
        claim_dir = os.path.join(self._base, claim_id)
        os.makedirs(claim_dir, exist_ok=True)
        path = os.path.join(claim_dir, filename)
        with open(path, "wb") as f:
            f.write(file_bytes)
        logger.info(
            "local_storage_saved", extra={"path": path, "size": len(file_bytes)}
        )
        return path

    async def get_path(self, filename: str, claim_id: str) -> str:
        """Return the expected file path for a stored upload without reading it.

        Args:
            filename: The filename as originally saved.
            claim_id: The claim identifier subdirectory.

        Returns:
            str: Full path to the file on disk.
        """
        return os.path.join(self._base, claim_id, filename)
