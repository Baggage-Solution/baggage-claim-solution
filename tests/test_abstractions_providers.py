from __future__ import annotations

import pytest

from backend.channel_provider.webhook_channel import WebhookChannelProvider
from backend.queue_provider.in_memory_queue import InMemoryQueueProvider
from backend.secrets_provider.env_secrets import EnvSecretsProvider


# ──────────────────────────────────────────────────────────────
# QueueProvider — InMemoryQueueProvider
# ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_in_memory_queue_enqueue_dequeue_roundtrip():
    queue = InMemoryQueueProvider()
    payload = {"claim_id": "CLM-001", "message": "hello"}

    message_id = await queue.enqueue(payload)
    assert isinstance(message_id, str) and message_id

    jobs = await queue.dequeue(max_messages=1)
    assert len(jobs) == 1
    assert jobs[0]["claim_id"] == "CLM-001"
    assert "_receipt_handle" in jobs[0]


@pytest.mark.asyncio
async def test_in_memory_queue_dequeue_empty_returns_empty_list():
    queue = InMemoryQueueProvider()
    jobs = await queue.dequeue(max_messages=5)
    assert jobs == []


@pytest.mark.asyncio
async def test_in_memory_queue_ack_removes_inflight_job():
    queue = InMemoryQueueProvider()
    await queue.enqueue({"claim_id": "CLM-002"})
    jobs = await queue.dequeue(max_messages=1)
    receipt_handle = jobs[0]["_receipt_handle"]

    assert receipt_handle in queue._inflight
    await queue.ack(receipt_handle)
    assert receipt_handle not in queue._inflight


@pytest.mark.asyncio
async def test_in_memory_queue_respects_max_messages():
    queue = InMemoryQueueProvider()
    for i in range(5):
        await queue.enqueue({"claim_id": f"CLM-{i}"})

    jobs = await queue.dequeue(max_messages=3)
    assert len(jobs) == 3

    remaining = await queue.dequeue(max_messages=10)
    assert len(remaining) == 2


# ──────────────────────────────────────────────────────────────
# SecretsProvider — EnvSecretsProvider
# ──────────────────────────────────────────────────────────────
def test_env_secrets_returns_existing_value(monkeypatch):
    monkeypatch.setenv("TEST_SECRET_KEY", "super-secret-value")
    provider = EnvSecretsProvider()
    assert provider.get("TEST_SECRET_KEY") == "super-secret-value"


def test_env_secrets_missing_key_raises_keyerror(monkeypatch):
    monkeypatch.delenv("TEST_SECRET_MISSING", raising=False)
    provider = EnvSecretsProvider()
    with pytest.raises(KeyError):
        provider.get("TEST_SECRET_MISSING")


# ──────────────────────────────────────────────────────────────
# ChannelProvider — WebhookChannelProvider
# ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_webhook_channel_pushes_to_session_sse_queue():
    from backend.agents.a5_notification import get_or_create_queue

    provider = WebhookChannelProvider()
    session_id = "test-session-abc"

    await provider.send_message(session_id, "Your claim was approved", attachments=None)

    queue = get_or_create_queue(session_id)
    event = queue.get_nowait()
    assert event["type"] == "message"
    assert event["text"] == "Your claim was approved"
    assert event["attachments"] == []


@pytest.mark.asyncio
async def test_webhook_channel_includes_attachments():
    from backend.agents.a5_notification import get_or_create_queue

    provider = WebhookChannelProvider()
    session_id = "test-session-xyz"
    attachments = [{"type": "image", "url": "https://example.com/voucher.png"}]

    await provider.send_message(session_id, "Voucher attached", attachments=attachments)

    queue = get_or_create_queue(session_id)
    event = queue.get_nowait()
    assert event["attachments"] == attachments


# ──────────────────────────────────────────────────────────────
# Dependency factory branches — default ("local") providers resolve
# ──────────────────────────────────────────────────────────────
def test_provide_queue_returns_in_memory_by_default():
    from backend.dependencies import provide_queue

    provide_queue.cache_clear()
    provider = provide_queue()
    assert isinstance(provider, InMemoryQueueProvider)


def test_provide_secrets_returns_env_by_default():
    from backend.dependencies import provide_secrets

    provide_secrets.cache_clear()
    provider = provide_secrets()
    assert isinstance(provider, EnvSecretsProvider)


def test_provide_channel_returns_webhook_by_default():
    from backend.dependencies import provide_channel

    provide_channel.cache_clear()
    provider = provide_channel()
    assert isinstance(provider, WebhookChannelProvider)
