"""scripts/smoke_test_week1_aws.py — P-012 Week 1 Integration Smoke Test.

Standalone script (NOT a pytest file) that simulates one claim end-to-end
with every PROVIDER env var flipped to its AWS variant:

    LLM_PROVIDER=bedrock   VISION_PROVIDER=bedrock   OCR_PROVIDER=bedrock
    STORAGE_PROVIDER=s3    QUEUE_PROVIDER=sqs        SECRETS_PROVIDER=aws_sm

Flow exercised (mirrors the real production path through webhook.py +
worker.py, just compressed into one process):

    1. Spin up moto mocks for S3, SQS, and Secrets Manager.
    2. Pre-create the bucket, the main queue + DLQ, and the secret —
       standing in for the resources P-013 (admin) will pre-create in
       the real AWS account.
    3. Patch boto3.client for Bedrock (moto has no Bedrock backend —
       same approach as tests/test_aws_providers.py).
    4. POST a synthetic claim turn into the FastAPI app's /webhook route
       in-process (httpx ASGI transport — no real network call).
    5. Since QUEUE_PROVIDER=sqs, the webhook enqueues and returns
       {"accepted": true, ...} instead of running inline.
    6. Pull the job back off the (mocked) SQS queue and feed it through
       backend.worker.process_job(), exactly as the real worker would.
    7. Assert the job was acked (i.e. deleted from the queue).

This script intentionally does NOT replace pytest. It is a one-shot,
human-readable trace for the "run a smoke test against a sample claim
with provider stubs" line item in the P-012 task tracker entry — run it
once, read the printed trace, and attach the output to
BRANCH_DOCS/AWS_PHASE/integration-week1.md.

Usage:
    python scripts/smoke_test_week1_aws.py

Exit code 0 on success, non-zero on any assertion failure.

Author: Devam — P-012
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, patch

# ── Force every PROVIDER switch to its AWS variant BEFORE importing any
#    backend module that reads settings at import time (config.py uses
#    @lru_cache, so the values must be set first). ────────────────────────────
os.environ["LLM_PROVIDER"] = "bedrock"
os.environ["VISION_PROVIDER"] = "bedrock"
os.environ["OCR_PROVIDER"] = "bedrock"
os.environ["STORAGE_PROVIDER"] = "s3"
os.environ["QUEUE_PROVIDER"] = "sqs"
os.environ["SECRETS_PROVIDER"] = "aws_sm"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["S3_BUCKET"] = "abc-baggage-claims-integration"
os.environ["SECRETS_MANAGER_NAME"] = "baggage-claim/integration"
os.environ.setdefault("ENABLE_SIMULATOR", "false")

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

TEST_REGION = "us-east-1"


def _print_step(label: str) -> None:
    print(f"\n{'─' * 70}\n{label}\n{'─' * 70}")


def _make_bedrock_text_response(text: str) -> dict:
    """Mirrors tests/conftest.py::make_bedrock_text_response — kept local
    so this script has zero import-order dependency on the test suite."""
    payload = {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(payload).encode("utf-8")
    return {"body": mock_body}


async def run_smoke_test() -> None:
    """Run the full AWS-flipped smoke test and print a step-by-step trace."""

    with mock_aws():
        # ── 1. Pre-create AWS resources (stand-in for P-013 admin work) ──────
        _print_step("STEP 1 — Pre-creating moto-mocked AWS resources")

        s3 = boto3.client("s3", region_name=TEST_REGION)
        s3.create_bucket(Bucket="abc-baggage-claims-integration")
        print("  ✅ S3 bucket created: abc-baggage-claims-integration")

        sqs = boto3.client("sqs", region_name=TEST_REGION)
        dlq = sqs.create_queue(QueueName="claim-jobs-dlq-integration")
        dlq_arn = sqs.get_queue_attributes(
            QueueUrl=dlq["QueueUrl"], AttributeNames=["QueueArn"]
        )["Attributes"]["QueueArn"]
        main_queue = sqs.create_queue(
            QueueName="claim-jobs-integration",
            Attributes={
                "VisibilityTimeout": "60",
                "RedrivePolicy": json.dumps(
                    {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"}
                ),
            },
        )
        os.environ["SQS_QUEUE_URL"] = main_queue["QueueUrl"]
        os.environ["SQS_DLQ_URL"] = dlq["QueueUrl"]
        print(f"  ✅ SQS queue created: {main_queue['QueueUrl']}")
        print(f"  ✅ SQS DLQ created:   {dlq['QueueUrl']}")

        secretsmanager = boto3.client("secretsmanager", region_name=TEST_REGION)
        secretsmanager.create_secret(
            Name="baggage-claim/integration",
            SecretString=json.dumps(
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_SERVICE_ROLE_KEY": "smoke-test-placeholder",
                }
            ),
        )
        print("  ✅ Secrets Manager secret created: baggage-claim/integration")

        # ── 2. Clear cached settings/providers so the new env vars + the
        #      freshly created resources above are actually picked up. ──────
        from backend.config import get_settings
        from backend.dependencies import (provide_llm, provide_ocr,
                                           provide_queue, provide_secrets,
                                           provide_storage, provide_vision)

        get_settings.cache_clear()
        provide_llm.cache_clear()
        provide_vision.cache_clear()
        provide_ocr.cache_clear()
        provide_storage.cache_clear()
        provide_queue.cache_clear()
        provide_secrets.cache_clear()

        settings = get_settings()
        _print_step("STEP 2 — Confirming provider wiring resolves to AWS classes")
        print(f"  llm_provider       = {settings.llm_provider}")
        print(f"  vision_provider    = {settings.vision_provider}")
        print(f"  ocr_provider       = {settings.ocr_provider}")
        print(f"  storage_provider   = {settings.storage_provider}")
        print(f"  queue_provider     = {settings.queue_provider}")
        print(f"  secrets_provider   = {settings.secrets_provider}")

        storage = provide_storage()
        queue = provide_queue()
        secrets = provide_secrets()
        assert type(storage).__name__ == "S3StorageProvider", type(storage)
        assert type(queue).__name__ == "SQSQueueProvider", type(queue)
        assert type(secrets).__name__ == "AWSSecretsManagerProvider", type(secrets)
        print("  ✅ provide_storage() → S3StorageProvider")
        print("  ✅ provide_queue()   → SQSQueueProvider")
        print("  ✅ provide_secrets() → AWSSecretsManagerProvider")

        # ── 3. Patch Bedrock (moto has no Bedrock backend) and POST a
        #      synthetic claim turn through the real FastAPI app. ───────────
        _print_step("STEP 3 — POST /webhook (QUEUE_PROVIDER=sqs path)")

        bedrock_response = _make_bedrock_text_response(
            "Hi! I'm sorry to hear about your bag. "
            "Could you describe the damage and send a photo?"
        )
        mock_bedrock_client = MagicMock()
        mock_bedrock_client.invoke_model.return_value = bedrock_response

        with patch("boto3.client", return_value=mock_bedrock_client):
            from httpx import ASGITransport, AsyncClient

            from backend.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://smoke-test"
            ) as client:
                response = await client.post(
                    "/webhook",
                    json={
                        "session_id": "smoke-week1-aws-001",
                        "message": "hi, my suitcase wheel snapped off in transit",
                    },
                )

        print(f"  HTTP status: {response.status_code}")
        body = response.json()
        print(f"  Response body: {json.dumps(body, indent=2)}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert body.get("accepted") is True, "Expected {'accepted': true} in SQS mode"
        assert "job_id" in body, "Expected job_id in enqueue response"
        print("  ✅ Webhook enqueued the job and returned 200 within budget")

        # ── 4. Pull the job back off SQS and run it through the real
        #      worker.process_job(), exactly as backend/worker.py does. ─────
        _print_step("STEP 4 — Dequeue + worker.process_job() (worker-side path)")

        from backend.dependencies import provide_channel
        from backend.worker import process_job

        channel = provide_channel()

        with patch("boto3.client", return_value=mock_bedrock_client):
            jobs = await queue.dequeue(max_messages=1)
            assert len(jobs) == 1, f"Expected 1 job on the queue, found {len(jobs)}"
            job = jobs[0]
            print(f"  Dequeued job_id={job.get('job_id')} session_id={job.get('session_id')}")

            await process_job(job, queue, channel)

        # ── 5. Confirm the message was acked (deleted) — not left for redrive.
        remaining = sqs.get_queue_attributes(
            QueueUrl=main_queue["QueueUrl"],
            AttributeNames=["ApproximateNumberOfMessages"],
        )["Attributes"]["ApproximateNumberOfMessages"]
        print(f"  Messages remaining on queue after ack: {remaining}")
        assert remaining == "0", "Job was not acked — still visible on queue"
        print("  ✅ Worker processed the job and acked it off SQS")

        _print_step("SMOKE TEST PASSED — full webhook → SQS → worker round-trip OK")


if __name__ == "__main__":
    try:
        asyncio.run(run_smoke_test())
    except AssertionError as exc:
        print(f"\n❌ SMOKE TEST FAILED: {exc}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ SMOKE TEST ERRORED: {exc!r}")
        raise