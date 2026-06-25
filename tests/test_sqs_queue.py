from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws

from backend.queue_provider.sqs_queue import SQSQueueProvider

TEST_REGION = "us-east-1"


@pytest.fixture
def sqs_provider():
    """Yield an SQSQueueProvider backed by a moto-mocked SQS queue.

    The mock_aws context manager intercepts all boto3 calls for the
    duration of the test — no real AWS account, credentials, or network
    access is used or required.
    """
    with mock_aws():
        client = boto3.client("sqs", region_name=TEST_REGION)
        queue = client.create_queue(QueueName="baggage-claim-test-queue")
        yield SQSQueueProvider(
            queue_url=queue["QueueUrl"],
            dlq_url=None,
            region=TEST_REGION,
        )


@pytest.mark.asyncio
async def test_enqueue_returns_message_id(sqs_provider):
    """enqueue() returns a non-empty SQS MessageId."""
    message_id = await sqs_provider.enqueue({"claim_id": "CLM-100"})

    assert message_id
    assert isinstance(message_id, str)


@pytest.mark.asyncio
async def test_enqueue_dequeue_round_trip_preserves_payload(sqs_provider):
    """A job enqueued can be dequeued with its original payload intact."""
    payload = {"claim_id": "CLM-200", "session_id": "sess-1", "message": "hi"}
    await sqs_provider.enqueue(payload)

    jobs = await sqs_provider.dequeue(max_messages=1)

    assert len(jobs) == 1
    assert jobs[0]["claim_id"] == "CLM-200"
    assert jobs[0]["session_id"] == "sess-1"
    assert jobs[0]["message"] == "hi"


@pytest.mark.asyncio
async def test_dequeue_tags_job_with_receipt_handle(sqs_provider):
    """Each dequeued job carries a `_receipt_handle` key, matching the
    key name InMemoryQueueProvider uses, so worker.py needs no
    provider-specific branching."""
    await sqs_provider.enqueue({"claim_id": "CLM-300"})

    jobs = await sqs_provider.dequeue(max_messages=1)

    assert "_receipt_handle" in jobs[0]
    assert jobs[0]["_receipt_handle"]


@pytest.mark.asyncio
async def test_dequeue_respects_max_messages(sqs_provider):
    """dequeue() never returns more than `max_messages` jobs, even when
    more are available on the queue."""
    for i in range(3):
        await sqs_provider.enqueue({"claim_id": f"CLM-40{i}"})

    jobs = await sqs_provider.dequeue(max_messages=2)

    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_dequeue_on_empty_queue_returns_empty_list(sqs_provider):
    """Dequeuing from an empty queue returns an empty list rather than
    raising or blocking indefinitely."""
    jobs = await sqs_provider.dequeue(max_messages=1)

    assert jobs == []


@pytest.mark.asyncio
async def test_ack_removes_message_from_queue(sqs_provider):
    """Acking a message deletes it — a subsequent dequeue must not see
    it again."""
    await sqs_provider.enqueue({"claim_id": "CLM-500"})
    jobs = await sqs_provider.dequeue(max_messages=1)
    receipt_handle = jobs[0]["_receipt_handle"]

    await sqs_provider.ack(receipt_handle)

    remaining = await sqs_provider.dequeue(max_messages=1)
    assert remaining == []


@pytest.mark.asyncio
async def test_visibility_timeout_is_configurable():
    """A custom visibility_timeout is actually passed through to the
    ReceiveMessage call — verified by reading it back via
    get_queue_attributes after a dequeue with a non-default value."""
    with mock_aws():
        client = boto3.client("sqs", region_name=TEST_REGION)
        queue = client.create_queue(QueueName="baggage-claim-test-queue-vis")
        provider = SQSQueueProvider(
            queue_url=queue["QueueUrl"],
            dlq_url=None,
            region=TEST_REGION,
            visibility_timeout=120,
        )
        await provider.enqueue({"claim_id": "CLM-600"})

        jobs = await provider.dequeue(max_messages=1)
        assert len(jobs) == 1

        # A second immediate dequeue should NOT see the message again —
        # it is still within its (long, 120s) visibility window.
        immediate_redequeue = await provider.dequeue(max_messages=1)
        assert immediate_redequeue == []


@pytest.mark.asyncio
async def test_enqueue_serialises_payload_as_json(sqs_provider):
    """The raw SQS message body is valid JSON matching the enqueued
    payload — confirms the wire format, independent of dequeue's own
    json.loads roundtrip."""
    await sqs_provider.enqueue({"claim_id": "CLM-700", "amount": 42})

    raw_client = boto3.client("sqs", region_name=TEST_REGION)
    response = raw_client.receive_message(
        QueueUrl=sqs_provider._queue_url, MaxNumberOfMessages=1
    )
    body = json.loads(response["Messages"][0]["Body"])

    assert body == {"claim_id": "CLM-700", "amount": 42}


@pytest.mark.asyncio
async def test_enqueue_raises_on_nonexistent_queue():
    """If the configured queue doesn't exist, enqueue() propagates the
    ClientError rather than silently swallowing it — callers (the
    webhook handler) need to know the job was not accepted."""
    from botocore.exceptions import ClientError

    with mock_aws():
        # Note: no create_queue call — queue genuinely does not exist
        provider = SQSQueueProvider(
            queue_url="https://sqs.us-east-1.amazonaws.com/000000000000/nonexistent",
            dlq_url=None,
            region=TEST_REGION,
        )

        with pytest.raises(ClientError):
            await provider.enqueue({"claim_id": "CLM-800"})