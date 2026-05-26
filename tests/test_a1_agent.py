"""
Tests for GeminiLLMProvider and A1ConversationAgent — T-008.
All LLM calls are mocked — no real API calls in test suite.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.a1_conversation import STEPS, A1ConversationAgent
from backend.graph.state import ClaimState

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_agent(
    reply: str = "Hello! Please describe the damage.",
) -> A1ConversationAgent:
    """Create A1 agent with a mocked LLM."""
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value=reply)
    return A1ConversationAgent(llm=mock_llm)


def make_state(**kwargs) -> ClaimState:
    """Create a ClaimState with sensible defaults."""
    defaults = {
        "session_id": "test-session-001",
        "passenger_message": "my bag is damaged",
        "conversation_step": "greeting",
    }
    defaults.update(kwargs)
    return ClaimState(**defaults)


# ── GeminiLLMProvider tests ───────────────────────────────────────────────────


def test_build_gemini_contents_converts_roles():
    """_build_gemini_contents converts 'assistant' → 'model' correctly."""
    from backend.llm_provider.gemini_llm import GeminiLLMProvider

    with patch("google.generativeai.configure"), patch(
        "google.generativeai.GenerativeModel"
    ):
        provider = GeminiLLMProvider(api_key="test-key")

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    result = provider._build_gemini_contents(messages)

    # System prepended to first user message
    assert result[0]["role"] == "user"
    assert "You are helpful." in result[0]["parts"][0]
    # Assistant → model
    assert result[1]["role"] == "model"


def test_build_gemini_contents_no_system():
    """_build_gemini_contents handles messages with no system prompt."""
    from backend.llm_provider.gemini_llm import GeminiLLMProvider

    with patch("google.generativeai.configure"), patch(
        "google.generativeai.GenerativeModel"
    ):
        provider = GeminiLLMProvider(api_key="test-key")

    messages = [{"role": "user", "content": "hi"}]
    result = provider._build_gemini_contents(messages)

    assert result[0]["role"] == "user"
    assert result[0]["parts"][0] == "hi"


# ── A1ConversationAgent tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a1_greeting_sets_response():
    """A1 sets a1_response on greeting step."""
    agent = make_agent(reply="Welcome! Please describe the damage to your bag.")
    state = make_state(conversation_step="greeting")

    result = await agent.handle(state, [])

    assert result.a1_response == "Welcome! Please describe the damage to your bag."
    assert result.error is None


@pytest.mark.asyncio
async def test_a1_advances_step():
    """A1 advances conversation_step from greeting to damage_photos."""
    agent = make_agent()
    state = make_state(conversation_step="greeting")

    result = await agent.handle(state, [])

    assert result.conversation_step == "damage_photos"


@pytest.mark.asyncio
async def test_a1_does_not_advance_past_result():
    """A1 stays at 'result' step — never goes beyond."""
    agent = make_agent()
    state = make_state(conversation_step="result", routing_lane=1)

    result = await agent.handle(state, [])

    assert result.conversation_step == "result"


@pytest.mark.asyncio
async def test_a1_re_request_tag_does_not_advance():
    """A1 does not advance step when re_request_tag is True."""
    agent = make_agent()
    state = make_state(
        conversation_step="tag_photo",
        re_request_tag=True,
    )

    result = await agent.handle(state, [])

    assert result.conversation_step == "tag_photo"


@pytest.mark.asyncio
async def test_a1_jumps_to_result_when_lane_set():
    """A1 jumps to 'result' step when A4 has set routing_lane."""
    agent = make_agent()
    state = make_state(
        conversation_step="confirm",
        routing_lane=1,
        voucher_code="VCH-TEST123",
        final_compensation_usd=50.0,
    )

    result = await agent.handle(state, [])

    assert result.conversation_step == "result"


@pytest.mark.asyncio
async def test_a1_sets_error_on_llm_failure():
    """A1 catches LLM exceptions and sets state.error instead of raising."""
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(side_effect=Exception("Gemini API timeout"))
    agent = A1ConversationAgent(llm=mock_llm)
    state = make_state()

    result = await agent.handle(state, [])

    assert result.error is not None
    assert "A1 error" in result.error


@pytest.mark.asyncio
async def test_a1_includes_conversation_history():
    """A1 includes conversation history in LLM call."""
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value="Please upload damage photos.")
    agent = A1ConversationAgent(llm=mock_llm)
    state = make_state(
        conversation_step="damage_photos",
        conversation_history=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello! Please describe the damage."},
        ],
    )

    await agent.handle(state, [])

    # Verify chat was called with messages including history
    call_args = mock_llm.chat.call_args
    messages = call_args[0][0]
    roles = [m["role"] for m in messages]
    assert "user" in roles


@pytest.mark.asyncio
async def test_a1_lane1_result_includes_voucher():
    """A1 result prompt for Lane 1 includes voucher code rendering."""
    agent = make_agent(reply="Your claim is approved! Voucher: VCH-TEST123")
    state = make_state(
        conversation_step="result",
        routing_lane=1,
        voucher_code="VCH-TEST123",
        final_compensation_usd=50.0,
    )

    result = await agent.handle(state, [])

    assert result.a1_response is not None
    assert result.error is None
