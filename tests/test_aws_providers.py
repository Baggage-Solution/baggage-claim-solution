"""tests/test_aws_providers.py — P-011: Cross-provider integration tests.

The individual providers (BedrockLLMProvider, BedrockVisionProvider,
BedrockOCRProvider, S3StorageProvider, AWSSecretsManagerProvider,
SQSQueueProvider) each already have a dedicated, isolated test file —
test_bedrock_llm.py, test_bedrock_vision.py, test_bedrock_ocr.py,
test_s3_storage.py, test_aws_secrets.py, test_sqs_queue.py — written and
merged as part of P-003 through P-006. This file does NOT duplicate that
coverage.

What THIS file covers instead:
  1. The factory wiring in dependencies.py actually instantiates the
     right concrete class for every AWS_* provider switch, end-to-end
     (not just "does the class exist" — that the *configured selection*
     produces the *correct* provider).
  2. A realistic cross-provider flow using the actual job payload shape
     (S3 upload -> SQS enqueue -> SQS dequeue -> verify payload integrity),
     mirroring how webhook.py and worker.py genuinely use multiple
     providers together in a single request lifecycle.
  3. That every provider switch still defaults correctly to its
     PROVIDER=local equivalent when AWS env vars are absent — the
     explicit P-011 acceptance criterion ("existing pytest suite must
     still pass with PROVIDER=local defaults").
  4. Moto does not support Bedrock — every Bedrock-touching assertion in
     this file uses unittest.mock.patch("boto3.client"), per the task's
     own note. Every other provider uses real moto mocks via @mock_aws.

Authors: Aditya — P-011
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from backend.config import get_settings
from tests.conftest import make_bedrock_text_response

TEST_REGION = "us-east-1"


@pytest.fixture(autouse=True)
def _clean_settings_cache():
    """Clear get_settings() AND every provide_*() lru_cache before and
    after every test in this file.

    Root-caused bug this fixes: provide_storage() (and its siblings) are
    @lru_cache'd in dependencies.py. A test that configures
    STORAGE_PROVIDER=s3 with no real AWS credentials and then calls
    provide_storage() leaves a constructed-but-uncallable S3StorageProvider
    sitting in that lru_cache for the rest of the pytest SESSION — not
    just this test, and not just this file. Any later test in the suite
    that calls provide_storage() fresh (e.g. test_t013_upload_endpoint_exists
    in test_smoke_t001_t016.py) silently inherits that broken cached
    instance instead of constructing its own, and fails with
    NoCredentialsError despite never touching AWS-related code itself.
    Clearing AFTER every test here, not just before, closes that gap.
    """
    get_settings.cache_clear()
    _clear_provider_caches()
    yield
    get_settings.cache_clear()
    _clear_provider_caches()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Prevent any AWS_* / *_PROVIDER env vars from leaking between tests
    via the real process environment."""
    for var in (
        "LLM_PROVIDER",
        "VISION_PROVIDER",
        "OCR_PROVIDER",
        "STORAGE_PROVIDER",
        "QUEUE_PROVIDER",
        "SECRETS_PROVIDER",
        "S3_BUCKET",
        "AWS_REGION",
        "SECRETS_MANAGER_NAME",
        "SQS_QUEUE_URL",
        "SQS_DLQ_URL",
    ):
        monkeypatch.delenv(var, raising=False)


def _clear_provider_caches():
    """Clear every provide_*() lru_cache. Local import to avoid a
    module-level import-time dependency on dependencies.py before env
    vars for a given test are set."""
    from backend.dependencies import (
        provide_llm,
        provide_ocr,
        provide_queue,
        provide_secrets,
        provide_storage,
        provide_vision,
    )

    for fn in (
        provide_llm,
        provide_vision,
        provide_ocr,
        provide_storage,
        provide_queue,
        provide_secrets,
    ):
        fn.cache_clear()


# ── 1. Factory wiring — every AWS_* provider switch resolves correctly ────────


def test_llm_provider_bedrock_resolves_to_bedrock_class(monkeypatch):
    """LLM_PROVIDER=bedrock actually instantiates BedrockLLMProvider, not
    just 'a class that exists somewhere'."""
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("AWS_REGION", TEST_REGION)
    _clear_provider_caches()

    from backend.dependencies import provide_llm
    from backend.llm_provider.bedrock_llm import BedrockLLMProvider

    assert isinstance(provide_llm(), BedrockLLMProvider)


def test_vision_provider_bedrock_resolves_to_bedrock_class(monkeypatch):
    """VISION_PROVIDER=bedrock actually instantiates BedrockVisionProvider."""
    monkeypatch.setenv("VISION_PROVIDER", "bedrock")
    monkeypatch.setenv("AWS_REGION", TEST_REGION)
    _clear_provider_caches()

    from backend.dependencies import provide_vision
    from backend.vision_provider.bedrock_vision import BedrockVisionProvider

    assert isinstance(provide_vision(), BedrockVisionProvider)


def test_ocr_provider_bedrock_resolves_to_bedrock_class(monkeypatch):
    """OCR_PROVIDER=bedrock actually instantiates BedrockOCRProvider."""
    monkeypatch.setenv("OCR_PROVIDER", "bedrock")
    monkeypatch.setenv("AWS_REGION", TEST_REGION)
    _clear_provider_caches()

    from backend.dependencies import provide_ocr
    from backend.ocr_provider.bedrock_ocr import BedrockOCRProvider

    assert isinstance(provide_ocr(), BedrockOCRProvider)


def test_storage_provider_s3_resolves_to_s3_class(monkeypatch):
    """STORAGE_PROVIDER=s3 actually instantiates S3StorageProvider."""
    monkeypatch.setenv("STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("S3_BUCKET", "abc-baggage-claims-test")
    monkeypatch.setenv("AWS_REGION", TEST_REGION)
    _clear_provider_caches()

    from backend.dependencies import provide_storage
    from backend.storage_provider.s3_storage import S3StorageProvider

    assert isinstance(provide_storage(), S3StorageProvider)


def test_queue_provider_sqs_resolves_to_sqs_class(monkeypatch):
    """QUEUE_PROVIDER=sqs actually instantiates SQSQueueProvider."""
    monkeypatch.setenv("QUEUE_PROVIDER", "sqs")
    monkeypatch.setenv(
        "SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/claim-jobs"
    )
    monkeypatch.setenv("AWS_REGION", TEST_REGION)
    _clear_provider_caches()

    from backend.dependencies import provide_queue
    from backend.queue_provider.sqs_queue import SQSQueueProvider

    assert isinstance(provide_queue(), SQSQueueProvider)


@mock_aws
def test_secrets_provider_aws_sm_resolves_to_aws_secrets_class(monkeypatch):
    """SECRETS_PROVIDER=aws_sm actually instantiates AWSSecretsManagerProvider."""
    client = boto3.client("secretsmanager", region_name=TEST_REGION)
    client.create_secret(
        Name="baggage-claim/test", SecretString=json.dumps({"SUPABASE_URL": "x"})
    )
    monkeypatch.setenv("SECRETS_PROVIDER", "aws_sm")
    monkeypatch.setenv("SECRETS_MANAGER_NAME", "baggage-claim/test")
    monkeypatch.setenv("AWS_REGION", TEST_REGION)
    _clear_provider_caches()

    from backend.dependencies import provide_secrets
    from backend.secrets_provider.aws_secrets import AWSSecretsManagerProvider

    assert isinstance(provide_secrets(), AWSSecretsManagerProvider)


# ── 2. Defaults to PROVIDER=local equivalents when unset ──────────────────────
# Explicit P-011 acceptance criterion: "Existing pytest suite must still
# pass with PROVIDER=local defaults."


def test_llm_provider_defaults_to_gemini():
    _clear_provider_caches()
    from backend.dependencies import provide_llm
    from backend.llm_provider.gemini_llm import GeminiLLMProvider

    assert isinstance(provide_llm(), GeminiLLMProvider)


def test_storage_provider_defaults_to_local():
    _clear_provider_caches()
    from backend.dependencies import provide_storage
    from backend.storage_provider.local_storage import LocalStorageProvider

    assert isinstance(provide_storage(), LocalStorageProvider)


def test_queue_provider_defaults_to_in_memory():
    _clear_provider_caches()
    from backend.dependencies import provide_queue
    from backend.queue_provider.in_memory_queue import InMemoryQueueProvider

    assert isinstance(provide_queue(), InMemoryQueueProvider)


def test_secrets_provider_defaults_to_env():
    _clear_provider_caches()
    from backend.dependencies import provide_secrets
    from backend.secrets_provider.env_secrets import EnvSecretsProvider

    assert isinstance(provide_secrets(), EnvSecretsProvider)


# ── 3. Cross-provider flow — S3 write, then SQS enqueue, then dequeue ─────────
# Mirrors how webhook.py genuinely uses StorageProvider and QueueProvider
# together in a single request: save the uploaded photo, then enqueue a
# job referencing it.


@pytest.mark.asyncio
async def test_s3_then_sqs_flow_preserves_job_payload(
    moto_s3_and_sqs, sample_claim_job
):
    """Save a file to S3, build a job payload referencing it, enqueue to
    SQS, dequeue, and confirm the payload survives the round-trip
    byte-for-byte (JSON round-trip through SQS can silently mangle types
    if not handled carefully — this test catches that)."""
    from backend.queue_provider.sqs_queue import SQSQueueProvider
    from backend.storage_provider.s3_storage import S3StorageProvider

    storage = S3StorageProvider(bucket=moto_s3_and_sqs["bucket"], region=TEST_REGION)
    queue = SQSQueueProvider(
        queue_url=moto_s3_and_sqs["queue_url"],
        dlq_url=moto_s3_and_sqs["dlq_url"],
        region=TEST_REGION,
    )

    claim_id = "CLM-INTEGRATION-001"
    s3_path = await storage.save(b"fake-jpeg-bytes", "damage_001.jpg", claim_id)

    job = dict(sample_claim_job)
    job["image_paths"] = [s3_path]

    job_id = await queue.enqueue(job)
    assert job_id

    dequeued = await queue.dequeue(max_messages=1)
    assert len(dequeued) == 1

    received_job = dequeued[0]
    receipt_handle = received_job.pop("_receipt_handle", None)

    # Every original field must survive the S3-save -> SQS-enqueue ->
    # SQS-dequeue round trip unchanged.
    for key, value in job.items():
        assert (
            received_job.get(key) == value
        ), f"field '{key}' mismatched after round-trip"

    if receipt_handle:
        await queue.ack(receipt_handle)


@pytest.mark.asyncio
async def test_s3_then_sqs_flow_with_tag_data(
    moto_s3_and_sqs, sample_claim_job_with_tag
):
    """Same round-trip as above, but with OCR/tag fields already populated
    — confirms nested-looking but flat OCR fields (flight_number, pnr,
    bag_id) also survive intact, since these are exactly the fields A4's
    decision logic depends on downstream."""
    from backend.queue_provider.sqs_queue import SQSQueueProvider
    from backend.storage_provider.s3_storage import S3StorageProvider

    storage = S3StorageProvider(bucket=moto_s3_and_sqs["bucket"], region=TEST_REGION)
    queue = SQSQueueProvider(
        queue_url=moto_s3_and_sqs["queue_url"],
        dlq_url=moto_s3_and_sqs["dlq_url"],
        region=TEST_REGION,
    )

    claim_id = "CLM-INTEGRATION-002"
    await storage.save(b"fake-tag-bytes", "tag_001.jpg", claim_id)

    job_id = await queue.enqueue(sample_claim_job_with_tag)
    assert job_id

    dequeued = await queue.dequeue(max_messages=1)
    received_job = dequeued[0]

    assert received_job["flight_number"] == "AI202"
    assert received_job["pnr"] == "ABC123"
    assert received_job["bag_id"] == "045230674234"
    assert received_job["tag_data_complete"] is True


@pytest.mark.asyncio
async def test_dlq_redrive_policy_is_correctly_configured(moto_s3_and_sqs):
    """The main queue's redrive policy points at the DLQ with
    maxReceiveCount=3 — confirms the fixture (and by extension, the real
    SQS setup it mirrors) wires the DLQ correctly, not just that a second
    queue happens to exist."""
    sqs = boto3.client("sqs", region_name=TEST_REGION)
    attrs = sqs.get_queue_attributes(
        QueueUrl=moto_s3_and_sqs["queue_url"], AttributeNames=["RedrivePolicy"]
    )
    redrive = json.loads(attrs["Attributes"]["RedrivePolicy"])
    # moto normalises maxReceiveCount to an int on read-back, even though
    # it was set as a string ("3") when the queue was created — matches
    # real AWS SQS's own behaviour (RedrivePolicy is stored as JSON, and
    # the API always returns maxReceiveCount as a JSON number). Comparing
    # against str(3) here would be testing this test's assumption, not
    # SQS's actual contract.
    assert redrive["maxReceiveCount"] == 3


# ── 4. Bedrock providers — unittest.mock only, never moto ─────────────────────
# moto has no Bedrock backend. Confirms the make_bedrock_text_response
# shared helper in conftest.py actually produces a usable mock for all
# three Bedrock providers, not just one.


@pytest.mark.asyncio
async def test_bedrock_llm_provider_with_shared_mock_helper():
    """BedrockLLMProvider.chat() works correctly against the shared
    make_bedrock_text_response() helper from conftest.py."""
    from backend.llm_provider.bedrock_llm import BedrockLLMProvider

    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.invoke_model.return_value = make_bedrock_text_response(
            "Hello from the shared fixture helper"
        )

        provider = BedrockLLMProvider(
            model_id="anthropic.claude-haiku-4-5-20251001-v1:0", region=TEST_REGION
        )
        reply = await provider.chat([{"role": "user", "content": "Hi"}])

    assert reply == "Hello from the shared fixture helper"


@pytest.mark.asyncio
async def test_bedrock_vision_provider_with_shared_mock_helper():
    """BedrockVisionProvider.analyze_image() works correctly against the
    shared make_bedrock_text_response() helper, with a JSON-encoded scene
    analysis as the response text."""
    from backend.vision_provider.bedrock_vision import BedrockVisionProvider

    scene_json = json.dumps(
        {
            "is_bag": True,
            "bag_confidence": 0.9,
            "object_description": "suitcase",
            "damage_types": [],
            "severity_score": 0.0,
            "damage_confidence": 0.8,
            "brand": None,
            "is_luxury": False,
            "brand_confidence": 0.0,
            "tag_visible": False,
            "tag_confidence": 0.0,
        }
    )

    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.invoke_model.return_value = make_bedrock_text_response(scene_json)

        provider = BedrockVisionProvider(
            model_id="anthropic.claude-haiku-4-5-20251001-v1:0", region=TEST_REGION
        )
        result = await provider.analyze_image("tests/fixtures/damaged/damaged_01.jpg")

    assert result.is_bag is True


@pytest.mark.asyncio
async def test_bedrock_ocr_provider_with_shared_mock_helper():
    """BedrockOCRProvider.extract_bag_tag() works correctly against the
    shared make_bedrock_text_response() helper."""
    from backend.ocr_provider.bedrock_ocr import BedrockOCRProvider

    tag_json = json.dumps(
        {
            "flight_number": "AI202",
            "pnr": "ABC123",
            "bag_id": "045230674234",
            "confidence": 0.95,
        }
    )

    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.invoke_model.return_value = make_bedrock_text_response(tag_json)

        provider = BedrockOCRProvider(
            model_id="anthropic.claude-haiku-4-5-20251001-v1:0", region=TEST_REGION
        )
        result = await provider.extract_bag_tag(
            "tests/fixtures/bag_tags/clear_tag_01.jpg"
        )

    assert result.flight_number == "AI202"
    assert result.pnr == "ABC123"
    assert result.bag_id == "045230674234"


# ── 5. Never call real AWS — sanity check on the test suite itself ───────────


def test_no_real_aws_credentials_required_to_run_this_file(monkeypatch):
    """Sanity check: explicitly unset any real AWS credential env vars
    before running provider instantiation, to prove construction alone
    never makes a network call (boto3 clients are lazy — they don't
    validate credentials until an actual API call is made)."""
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("S3_BUCKET", "abc-baggage-claims-test")
    monkeypatch.setenv("AWS_REGION", TEST_REGION)
    _clear_provider_caches()

    from backend.dependencies import provide_storage

    # Constructing the provider must not raise, even with zero AWS
    # credentials anywhere in the environment — boto3 only fails on the
    # first actual API call, which this test deliberately never makes.
    provider = provide_storage()
    assert provider is not None
