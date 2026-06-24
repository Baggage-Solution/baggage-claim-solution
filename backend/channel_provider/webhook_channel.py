from __future__ import annotations

import logging
from typing import Any

from backend.agents.a5_notification import get_or_create_queue
from backend.channel_provider.base import ChannelProvider

logger = logging.getLogger(__name__)


class WebhookChannelProvider(ChannelProvider):
    """
    Default channel impl — pushes onto the existing per-session SSE queue
    used by the simulator (POC — zero cost, zero behaviour change).
    Future swap: set CHANNEL_PROVIDER=whatsapp → whatsapp_channel.py (P-024),
    which posts to N8N's outbound webhook instead of an in-process queue.
    """

    async def send_message(
        self,
        session_id: str,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        """Push a message onto the session's SSE queue for the simulator to consume.

        Args:
            session_id: The conversation/session identifier.
            text: Message body to send.
            attachments: Optional list of attachment descriptors.
        """
        queue = get_or_create_queue(session_id)
        event = {"type": "message", "text": text, "attachments": attachments or []}
        await queue.put(event)
        logger.info("webhook_channel_sent", extra={"session_id": session_id})
