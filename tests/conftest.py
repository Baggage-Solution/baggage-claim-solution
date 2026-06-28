"""tests/conftest.py — Shared fixtures for AWS provider tests (P-011).

This file provides fixtures shared ACROSS multiple provider test files.
It does not replace or refactor the existing self-contained fixtures
already living inside test_s3_storage.py, test_sqs_queue.py,
test_aws_secrets.py, test_bedrock_llm.py, test_bedrock_vision.py, or
test_bedrock_ocr.py — those were written and merged as part of P-004,
P-005, P-006, and P-003 respectively, are already passing, and changing
them now would be scope creep with no benefit. This file exists for
fixtures that did NOT exist yet: a realistic sample claim job payload
(matching the exact shape webhook.py::_build_job_payload() produces) for
cross-provider integration-style tests in test_aws_providers.py, plus a
couple of small multi-service moto helpers.

Authors: Aditya — P-011
"""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

TEST_REGION = "us-east-1"


@pytest.fixture
def sample_claim_job() -> Dict[str, Any]:
    """A realistic claim job payload, matching the exact shape produced by
    backend/api/routes/webhook.py::_build_job_payload() and consumed by
    backend/worker.py::_rebuild_state_from_job().

    Using the real field names/shape here (rather than an invented
    simplified dict) means a test built on this fixture exercises the
    actual producer/consumer contract between the webhook and the worker,
    not a fictional one that could silently drift from reality.
    """
    return {
        "job_id": "test-job-00000000-0000-0000-0000-000000000001",
        "request_id": "test-request-id-001",
        "session_id": "test-session-001",
        "message": "Here's a photo of my damaged bag",
        "image_paths": ["tests/fixtures/damaged/damaged_01.jpg"],
        "conversation_history": [],
        "conversation_step": "awaiting_damage_photo",
        "conversation_ended": False,
        "no_damage_detected": False,
        "not_a_bag": False,
        "last_object_description": None,
        "non_bag_attempts": 0,
        "tag_in_damage_photo": False,
        "tag_candidate_paths": [],
        "processed_damage_paths": [],
        "damage_types": [],
        "severity_score": 0.0,
        "brand_detected": None,
        "is_luxury": False,
        "compensation_estimate_usd": 0.0,
        "processed_tag_paths": [],
        "flight_number": None,
        "pnr": None,
        "bag_id": None,
        "ocr_confidence": 0.0,
        "tag_data_complete": False,
        "tag_manually_entered": False,
        "manual_tag_text": None,
        "manual_flight_number": None,
        "manual_pnr": None,
        "manual_bag_id": None,
        "offer_manual_entry": False,
    }


@pytest.fixture
def sample_claim_job_with_tag(sample_claim_job) -> Dict[str, Any]:
    """Variant of sample_claim_job with tag/OCR fields already populated —
    useful for tests exercising the post-OCR stage of the pipeline without
    needing to run OCR in the test itself."""
    job = dict(sample_claim_job)
    job.update(
        {
            "processed_tag_paths": ["tests/fixtures/bag_tags/clear_tag_01.jpg"],
            "flight_number": "AI202",
            "pnr": "ABC123",
            "bag_id": "045230674234",
            "ocr_confidence": 0.95,
            "tag_data_complete": True,
        }
    )
    return job


def make_bedrock_text_response(text: str, stop_reason: str = "end_turn") -> dict:
    """Build a mock matching boto3's bedrock-runtime invoke_model response
    shape for a single text content block. Shared helper so
    test_aws_providers.py doesn't have to redefine this — moto has no
    Bedrock backend (confirmed), so this always pairs with
    unittest.mock.patch("boto3.client"), never with @mock_aws.
    """
    payload = {
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
    }
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(payload).encode("utf-8")
    return {"body": mock_body}


@pytest.fixture
def moto_s3_and_sqs():
    """Spin up a single moto context with BOTH an S3 bucket and an SQS
    queue pre-created — for integration-style tests in
    test_aws_providers.py that exercise a storage write followed by a
    queue enqueue in the same test, mirroring how webhook.py actually
    uses both providers together in one request.

    Yields a dict of {bucket, queue_url, dlq_url} so the test doesn't
    need to know moto's internal account-ID placeholder.
    """
    with mock_aws():
        s3 = boto3.client("s3", region_name=TEST_REGION)
        bucket = "abc-baggage-claims-test"
        s3.create_bucket(Bucket=bucket)

        sqs = boto3.client("sqs", region_name=TEST_REGION)
        dlq = sqs.create_queue(QueueName="claim-jobs-dlq-test")
        dlq_arn = sqs.get_queue_attributes(
            QueueUrl=dlq["QueueUrl"], AttributeNames=["QueueArn"]
        )["Attributes"]["QueueArn"]
        main_queue = sqs.create_queue(
            QueueName="claim-jobs-test",
            Attributes={
                "VisibilityTimeout": "60",
                "RedrivePolicy": json.dumps(
                    {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"}
                ),
            },
        )

        yield {
            "bucket": bucket,
            "queue_url": main_queue["QueueUrl"],
            "dlq_url": dlq["QueueUrl"],
        }
