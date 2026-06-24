from __future__ import annotations

import asyncio
import logging
import mimetypes

import boto3
from botocore.exceptions import ClientError

from backend.storage_provider.base import StorageProvider

logger = logging.getLogger(__name__)


class S3StorageProvider(StorageProvider):
    """
    AWS S3 storage (Production — pay-per-use).
    Saves uploads to s3://{bucket}/{claim_id}/{filename}.
    get_path returns a presigned GET URL (time-limited) instead of a raw
    s3:// URI, so downstream consumers (vision/OCR providers, browser
    previews) can fetch the object over plain HTTPS without needing AWS
    credentials of their own.

    Swap path: set STORAGE_PROVIDER=local to fall back to disk (POC),
    or implement a new StorageProvider for another object store — no
    other code changes required.
    """

    def __init__(
        self,
        bucket: str,
        region: str,
        presign_expiry_seconds: int = 3600,
    ) -> None:
        """Initialise the S3-backed storage provider.

        Args:
            bucket: Target S3 bucket name (e.g. abc-baggage-claims-prod).
            region: AWS region the bucket lives in (e.g. us-east-1).
            presign_expiry_seconds: TTL for presigned URLs returned by
                get_path. Defaults to 1 hour.
        """
        self._bucket = bucket
        self._presign_expiry = presign_expiry_seconds
        self._client = boto3.client("s3", region_name=region)

    async def save(self, file_bytes: bytes, filename: str, claim_id: str) -> str:
        """Upload raw file bytes to S3 under {claim_id}/{filename}.

        Mirrors LocalStorageProvider's directory-per-claim convention so
        existing callers (webhook.py /upload route) need no changes beyond
        the STORAGE_PROVIDER env var. boto3 is synchronous, so the actual
        PutObject call is offloaded to a thread to keep this coroutine
        non-blocking for the FastAPI event loop.

        Args:
            file_bytes: Raw bytes of the uploaded image.
            filename: Target filename (e.g. damage_001.jpg).
            claim_id: Claim or session identifier — becomes the S3 key prefix.
                Required so IAM bucket policies and lifecycle rules can scope
                by claim, and so accidental key collisions across claims are
                impossible.

        Returns:
            str: The S3 URI of the stored object — s3://{bucket}/{key}.

        Raises:
            ClientError: If the PutObject call fails (e.g. bucket missing,
                insufficient permissions, region mismatch).
        """
        key = f"{claim_id}/{filename}"
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=file_bytes,
                ContentType=self._guess_content_type(filename),
            )
        except ClientError:
            logger.exception(
                "s3_storage_save_failed",
                extra={"bucket": self._bucket, "key": key, "size": len(file_bytes)},
            )
            raise

        logger.info(
            "s3_storage_saved",
            extra={"bucket": self._bucket, "key": key, "size": len(file_bytes)},
        )
        return f"s3://{self._bucket}/{key}"

    async def get_path(self, filename: str, claim_id: str) -> str:
        """Return a presigned HTTPS URL for a previously stored object.

        Unlike LocalStorageProvider.get_path (which returns a raw filesystem
        path), this returns a time-limited presigned URL. Vision/OCR
        providers and any browser-facing preview can fetch the object
        directly over HTTPS without holding AWS credentials. The presign
        call itself does not touch the network — it is a local signature
        computation — so no thread offload is needed.

        Args:
            filename: The filename as originally saved.
            claim_id: The claim identifier used as the S3 key prefix.

        Returns:
            str: A presigned GET URL valid for `presign_expiry_seconds`.

        Raises:
            ClientError: If presigned URL generation fails.
        """
        key = f"{claim_id}/{filename}"
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=self._presign_expiry,
            )
        except ClientError:
            logger.exception(
                "s3_storage_presign_failed",
                extra={"bucket": self._bucket, "key": key},
            )
            raise
        return url

    @staticmethod
    def _guess_content_type(filename: str) -> str:
        """Best-effort Content-Type for the given filename.

        Delegates to Python's standard `mimetypes` module rather than a
        hand-maintained extension table — it covers far more types, is
        maintained by Python core, and needs no updates as new upload
        formats are added.

        Args:
            filename: The filename to inspect.

        Returns:
            str: A MIME type. Falls back to application/octet-stream when
            the extension is unrecognised.
        """
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or "application/octet-stream"
