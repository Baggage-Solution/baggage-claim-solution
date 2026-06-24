from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class QueueProvider(ABC):
    """
    Abstract interface for the job queue between the webhook (producer)
    and the worker (consumer). Swap by changing QUEUE_PROVIDER env var.
    Future: implement SQSQueueProvider (P-006) backed by Amazon SQS.
    """

    @abstractmethod
    async def enqueue(self, payload: dict[str, Any]) -> str:
        """Push a job onto the queue.

        Args:
            payload: JSON-serialisable job payload (claim_id, session_id, etc).

        Returns:
            str: A message/job identifier.
        """
        raise NotImplementedError

    @abstractmethod
    async def dequeue(self, max_messages: int = 1) -> list[dict[str, Any]]:
        """Pull up to `max_messages` jobs off the queue.

        Args:
            max_messages: Maximum number of jobs to retrieve in one call.

        Returns:
            list[dict]: Job payloads, each including a receipt handle the
            caller must pass back to `ack`.
        """
        raise NotImplementedError

    @abstractmethod
    async def ack(self, receipt_handle: str) -> None:
        """Acknowledge successful processing of a job, removing it from the queue.

        Args:
            receipt_handle: The handle returned alongside the job in `dequeue`.
        """
        raise NotImplementedError
