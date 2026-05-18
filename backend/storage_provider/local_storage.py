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
        claim_dir = os.path.join(self._base, claim_id)
        os.makedirs(claim_dir, exist_ok=True)
        path = os.path.join(claim_dir, filename)
        with open(path, "wb") as f:
            f.write(file_bytes)
        logger.info("local_storage_saved", extra={"path": path, "size": len(file_bytes)})
        return path

    async def get_path(self, filename: str, claim_id: str) -> str:
        return os.path.join(self._base, claim_id, filename)
