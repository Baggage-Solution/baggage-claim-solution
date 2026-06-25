from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

from backend.queue_provider.base import QueueProvider

logger = logging.getLogger(__name__)


class SQSQueueProvider(QueueProvider):
    """
    AWS SQS-backed queue (Production — pay-per-use).

    Decouples the webhook (producer) from the worker (consumer) via a
    durable, multi-process-safe queue. Long-polls on receive
    (WaitTimeSeconds=20) to minimise empty-receive cost. Visibility
    timeout is sized to the Bedrock latency budget so an in-flight
    message isn't redelivered to a second worker while the first is
    still processing it.

    Uses SQS Standard (not FIFO) — at-least-once delivery, occasional
    redelivery is possible. Deduplication is handled at the application
    level via claim_id, not by SQS.

    Swap path: set QUEUE_PROVIDER=memory to fall back to the in-process
    deque (POC/dev), or implement a new QueueProvider for another broker
    (e.g. Redis, RabbitMQ) — no other code changes required.
    """

    def __init__(
        self,
        queue_url: str,
        dlq_url: str | None,
        region: str,
        visibility_timeout: int = 60,
    ) -> None:
        """Initialise the SQS-backed queue provider.

        Args:
            queue_url: URL of the primary SQS queue (Standard, not FIFO).
            dlq_url: URL of the dead-letter queue. Not used directly by
                this provider (the DLQ redrive policy is configured on
                the queue itself), but kept for observability/tooling
                that needs to inspect the DLQ.
            region: AWS region the queue lives in (e.g. us-east-1).
            visibility_timeout: Seconds a dequeued message is hidden
                from other consumers before it becomes visible again.
                Sized to the Bedrock latency budget so in-flight jobs
                aren't redelivered mid-processing. Defaults to 60s.
        """
        self._queue_url = queue_url
        self._dlq_url = dlq_url
        self._visibility_timeout = visibility_timeout
        self._client = boto3.client("sqs", region_name=region)

    async def enqueue(self, payload: dict[str, Any]) -> str:
        """Send a job onto the SQS queue.

        boto3 is synchronous, so the actual SendMessage call is offloaded
        to a thread to keep this coroutine non-blocking for the FastAPI
        event loop — mirrors the asyncio.to_thread pattern used by
        S3StorageProvider.

        Args:
            payload: JSON-serialisable job payload (claim_id, session_id,
                message, image_paths, conversation_step, history, etc).

        Returns:
            str: The SQS MessageId for the enqueued job.

        Raises:
            ClientError: If the SendMessage call fails (e.g. queue
                missing, insufficient permissions).
        """
        try:
            response = await asyncio.to_thread(
                self._client.send_message,
                QueueUrl=self._queue_url,
                MessageBody=json.dumps(payload),
            )
        except ClientError:
            logger.exception(
                "sqs_queue_enqueue_failed",
                extra={"queue_url": self._queue_url},
            )
            raise

        message_id = response["MessageId"]
        logger.info("sqs_queue_enqueued", extra={"message_id": message_id})
        return message_id

    async def dequeue(self, max_messages: int = 1) -> list[dict[str, Any]]:
        """Long-poll up to `max_messages` jobs off the SQS queue.

        Uses WaitTimeSeconds=20 (long-polling) to reduce empty-receive
        cost compared to tight-loop short polling. Each returned job is
        tagged with `_receipt_handle`, matching the key name used by
        InMemoryQueueProvider so worker.py needs no provider-specific
        branching.

        Args:
            max_messages: Maximum number of jobs to retrieve in one
                call. SQS caps this at 10 per ReceiveMessage call.

        Returns:
            list[dict]: Job payloads, each including a `_receipt_handle`
            key the caller must pass back to `ack`.

        Raises:
            ClientError: If the ReceiveMessage call fails.
        """
        try:
            response = await asyncio.to_thread(
                self._client.receive_message,
                QueueUrl=self._queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=20,
                VisibilityTimeout=self._visibility_timeout,
            )
        except ClientError:
            logger.exception(
                "sqs_queue_dequeue_failed",
                extra={"queue_url": self._queue_url},
            )
            raise

        messages = response.get("Messages", [])
        results: list[dict[str, Any]] = []
        for message in messages:
            job = json.loads(message["Body"])
            job["_receipt_handle"] = message["ReceiptHandle"]
            results.append(job)

        if results:
            logger.info("sqs_queue_dequeued", extra={"count": len(results)})
        return results

    async def ack(self, receipt_handle: str) -> None:
        """Delete a message from the SQS queue, acknowledging processing.

        Args:
            receipt_handle: The handle returned alongside the job in
                `dequeue`.

        Raises:
            ClientError: If the DeleteMessage call fails.
        """
        try:
            await asyncio.to_thread(
                self._client.delete_message,
                QueueUrl=self._queue_url,
                ReceiptHandle=receipt_handle,
            )
        except ClientError:
            logger.exception(
                "sqs_queue_ack_failed",
                extra={"queue_url": self._queue_url},
            )
            raise

        logger.info("sqs_queue_acked", extra={"receipt_handle": receipt_handle})