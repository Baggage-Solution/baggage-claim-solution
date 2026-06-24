from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ChannelProvider(ABC):
    """
    Abstract interface for sending a reply back to the passenger.
    Swap by changing CHANNEL_PROVIDER env var.
    Future: implement WhatsAppChannelProvider (P-024) which posts to an
    N8N outbound webhook instead of pushing over SSE.
    """

    @abstractmethod
    async def send_message(
        self,
        session_id: str,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        """Deliver a message to the passenger on this channel.

        Args:
            session_id: The conversation/session identifier.
            text: Message body to send.
            attachments: Optional list of attachment descriptors (e.g. images).
        """
        raise NotImplementedError
