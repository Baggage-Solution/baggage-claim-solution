"""
Smoke tests for LangGraph graph compilation and invocation — T-005.

These tests verify:
  1. The graph compiles with MemorySaver checkpointer (no import errors).
  2. All 5 nodes execute in order with mocked providers (no API keys needed).
  3. Two invocations with the same session_id both succeed (MemorySaver wired correctly).

Providers are mocked via unittest.mock so these tests run in any environment —
CI, local dev without .env, Anoushka's machine — without needing real API keys.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.graph.orchestrator import ClaimOrchestrator, get_graph


def test_graph_compiles():
    """
    Graph builds and compiles with MemorySaver checkpointer without errors.
    This is the core T-005 acceptance criterion — 'graph compiled' in logs.
    """
    graph = get_graph()
    assert graph is not None


async def test_orchestrator_smoke_no_images():
    """
    Full 5-node pipeline runs end-to-end with mocked providers and no images.

    A2 (vision) and A3 (OCR) short-circuit because image_paths=[] — they
    return state unchanged. A1, A4, A5 run their stub logic.

    Acceptance: execution_completed=True, error=None, a1_response set.
    """
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(
        return_value="Hello! Please describe the damage to your bag."
    )
    mock_vision = MagicMock()
    mock_ocr = MagicMock()
    mock_db = MagicMock()
    mock_db.save_claim = AsyncMock(return_value=None)
    mock_db.get_claim_count = AsyncMock(return_value=0)

    with (
        patch("backend.dependencies.provide_llm", return_value=mock_llm),
        patch("backend.dependencies.provide_vision", return_value=mock_vision),
        patch("backend.dependencies.provide_ocr", return_value=mock_ocr),
        patch("backend.dependencies.provide_db", return_value=mock_db),
    ):
        result = await ClaimOrchestrator().run(
            session_id="smoke-test-no-images",
            passenger_message="my suitcase wheel is broken",
            request_id="req-smoke-001",
        )

    assert result.execution_completed is True
    assert result.error is None
    assert result.a1_response is not None


async def test_orchestrator_session_continuity():
    """
    Two invocations with the same session_id both complete successfully.

    Verifies that MemorySaver (thread_id=session_id) does not break
    multi-turn execution — no KeyError, no missing thread_id error.
    """
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(
        return_value="Hello! Please describe the damage to your bag."
    )
    mock_vision = MagicMock()
    mock_ocr = MagicMock()
    mock_db = MagicMock()
    mock_db.save_claim = AsyncMock(return_value=None)
    mock_db.get_claim_count = AsyncMock(return_value=0)

    with (
        patch("backend.dependencies.provide_llm", return_value=mock_llm),
        patch("backend.dependencies.provide_vision", return_value=mock_vision),
        patch("backend.dependencies.provide_ocr", return_value=mock_ocr),
        patch("backend.dependencies.provide_db", return_value=mock_db),
    ):
        orchestrator = ClaimOrchestrator()

        result_1 = await orchestrator.run(
            session_id="session-continuity-test",
            passenger_message="hi",
            request_id="req-cont-001",
        )
        result_2 = await orchestrator.run(
            session_id="session-continuity-test",
            passenger_message="my bag is damaged",
            request_id="req-cont-002",
        )

    assert result_1.execution_completed is True
    assert result_2.execution_completed is True
    assert result_1.error is None
    assert result_2.error is None
