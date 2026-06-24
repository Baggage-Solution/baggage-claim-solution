from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from typing import Any

from backend.queue_provider.base import QueueProvider

logger = logging.getLogger(__name__)


class InMemoryQueueProvider(QueueProvider):
    """
    In-process queue backed by a deque (POC / local dev — zero cost).
    Not durable across restarts and not safe across multiple processes.
    Future swap: set QUEUE_PROVIDER=sqs → sqs_queue.py (P-006).
    """

    def __init__(self) -> None:
        self._queue: deque[dict[str, Any]] = deque()
        self._lock = asyncio.Lock()
        self._inflight: dict[str, dict[str, Any]] = {}

    async def enqueue(self, payload: dict[str, Any]) -> str:
        """Append a job to the in-memory deque.

        Args:
            payload: JSON-serialisable job payload.

        Returns:
            str: Generated message id.
        """
        message_id = str(uuid.uuid4())
        async with self._lock:
            self._queue.append({"_message_id": message_id, **payload})
        logger.info("in_memory_queue_enqueued", extra={"message_id": message_id})
        return message_id

    async def dequeue(self, max_messages: int = 1) -> list[dict[str, Any]]:
        """Pop up to `max_messages` jobs from the front of the deque.

        Args:
            max_messages: Maximum number of jobs to retrieve.

        Returns:
            list[dict]: Jobs, each tagged with a `_receipt_handle` key.
        """
        results: list[dict[str, Any]] = []
        async with self._lock:
            for _ in range(min(max_messages, len(self._queue))):
                job = self._queue.popleft()
                receipt_handle = str(uuid.uuid4())
                self._inflight[receipt_handle] = job
                results.append({**job, "_receipt_handle": receipt_handle})
        if results:
            logger.info("in_memory_queue_dequeued", extra={"count": len(results)})
        return results

    async def ack(self, receipt_handle: str) -> None:
        """Remove a job from the in-flight tracking dict.

        Args:
            receipt_handle: Handle returned by `dequeue`.
        """
        async with self._lock:
            self._inflight.pop(receipt_handle, None)
        logger.info("in_memory_queue_acked", extra={"receipt_handle": receipt_handle})
