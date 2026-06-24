from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from backend.storage_provider.s3_storage import S3StorageProvider

TEST_BUCKET = "abc-baggage-claims-test"
TEST_REGION = "us-east-1"


@pytest.fixture
def s3_provider():
    """Yield an S3StorageProvider backed by a moto-mocked S3 bucket.

    The mock_aws context manager intercepts all boto3 calls for the
    duration of the test — no real AWS account, credentials, or network
    access is used or required.
    """
    with mock_aws():
        client = boto3.client("s3", region_name=TEST_REGION)
        client.create_bucket(Bucket=TEST_BUCKET)
        yield S3StorageProvider(bucket=TEST_BUCKET, region=TEST_REGION)


@pytest.mark.asyncio
async def test_save_returns_s3_uri(s3_provider):
    """save() returns an s3:// URI scoped under the claim_id prefix."""
    path = await s3_provider.save(b"fake-image-bytes", "damage_001.jpg", "CLM-100")

    assert path == f"s3://{TEST_BUCKET}/CLM-100/damage_001.jpg"


@pytest.mark.asyncio
async def test_save_persists_object_with_correct_key_and_body(s3_provider):
    """The object actually lands in the bucket under {claim_id}/{filename}
    with the exact bytes that were uploaded."""
    await s3_provider.save(b"hello-bytes", "tag_001.jpg", "CLM-200")

    raw_client = boto3.client("s3", region_name=TEST_REGION)
    obj = raw_client.get_object(Bucket=TEST_BUCKET, Key="CLM-200/tag_001.jpg")

    assert obj["Body"].read() == b"hello-bytes"


@pytest.mark.asyncio
async def test_save_sets_content_type_for_jpeg(s3_provider):
    """JPEG uploads get an image/jpeg Content-Type for correct browser/
    vision-provider handling."""
    await s3_provider.save(b"jpeg-bytes", "damage_002.jpeg", "CLM-300")

    raw_client = boto3.client("s3", region_name=TEST_REGION)
    obj = raw_client.get_object(Bucket=TEST_BUCKET, Key="CLM-300/damage_002.jpeg")

    assert obj["ContentType"] == "image/jpeg"


@pytest.mark.asyncio
async def test_save_falls_back_to_octet_stream_for_unknown_extension(s3_provider):
    """Truly unrecognised extensions still upload successfully with a safe
    default Content-Type rather than raising. (.qqzzz is not a registered
    extension in Python's mimetypes database — unlike .xyz, which actually
    resolves to 'chemical/x-xyz' and would make a poor test case here.)"""
    await s3_provider.save(b"binary-bytes", "weird_file.qqzzz", "CLM-400")

    raw_client = boto3.client("s3", region_name=TEST_REGION)
    obj = raw_client.get_object(Bucket=TEST_BUCKET, Key="CLM-400/weird_file.qqzzz")

    assert obj["ContentType"] == "application/octet-stream"


@pytest.mark.asyncio
async def test_get_path_returns_presigned_https_url(s3_provider):
    """get_path() returns a presigned HTTPS URL (not a raw s3:// URI),
    so consumers without AWS credentials can fetch the object directly."""
    await s3_provider.save(b"some-bytes", "damage_003.jpg", "CLM-500")

    url = await s3_provider.get_path("damage_003.jpg", "CLM-500")

    assert url.startswith("https://")
    assert "CLM-500/damage_003.jpg" in url


@pytest.mark.asyncio
async def test_get_path_respects_custom_expiry():
    """Presign expiry is configurable per-instance and changes the
    generated URL's expiry parameter (Expires for SigV2-style presigning,
    or X-Amz-Expires for SigV4 — boto3/moto may return either depending on
    the signature version negotiated; this test checks for whichever the
    environment produces rather than hardcoding one).
    """
    with mock_aws():
        client = boto3.client("s3", region_name=TEST_REGION)
        client.create_bucket(Bucket=TEST_BUCKET)
        short = S3StorageProvider(
            bucket=TEST_BUCKET, region=TEST_REGION, presign_expiry_seconds=120
        )
        long_ = S3StorageProvider(
            bucket=TEST_BUCKET, region=TEST_REGION, presign_expiry_seconds=7200
        )
        await short.save(b"bytes", "tag_002.jpg", "CLM-600")

        url_short = await short.get_path("tag_002.jpg", "CLM-600")
        url_long = await long_.get_path("tag_002.jpg", "CLM-600")

        # Different TTLs must produce different expiry values in the URL —
        # proves presign_expiry_seconds is actually wired through, without
        # hardcoding a specific query-param name that varies by sig version.
        assert url_short != url_long


@pytest.mark.asyncio
async def test_save_different_claims_do_not_collide(s3_provider):
    """Two claims uploading a file with the identical filename must not
    overwrite each other — the claim_id prefix keeps keys distinct."""
    await s3_provider.save(b"claim-a-bytes", "damage_001.jpg", "CLM-700")
    await s3_provider.save(b"claim-b-bytes", "damage_001.jpg", "CLM-701")

    raw_client = boto3.client("s3", region_name=TEST_REGION)
    obj_a = raw_client.get_object(Bucket=TEST_BUCKET, Key="CLM-700/damage_001.jpg")
    obj_b = raw_client.get_object(Bucket=TEST_BUCKET, Key="CLM-701/damage_001.jpg")

    assert obj_a["Body"].read() == b"claim-a-bytes"
    assert obj_b["Body"].read() == b"claim-b-bytes"


@pytest.mark.asyncio
async def test_save_raises_on_nonexistent_bucket():
    """If the configured bucket doesn't exist, save() propagates the
    ClientError rather than silently swallowing it — callers (webhook.py)
    need to know the upload failed."""
    from botocore.exceptions import ClientError

    with mock_aws():
        # Note: no create_bucket call — bucket genuinely does not exist
        provider = S3StorageProvider(bucket="nonexistent-bucket", region=TEST_REGION)

        with pytest.raises(ClientError):
            await provider.save(b"bytes", "file.jpg", "CLM-800")
