"""
Integration tests for full Lane 1 and Lane 2 claim flows — T-020.

Tests the complete 5-agent pipeline end-to-end using mocked providers.
No real API keys, Supabase connections, or Gemini calls are made.

Coverage:
  Lane 1 — Standard bag, low value → auto-approve → VCH- voucher issued
  Lane 2 — Luxury bag → staff review → hitl_queued=True, no voucher
  Retry flow — Blurry tag → re_request_tag set → A4 skips → no routing
  Error resilience — DB failure does not prevent routing decision

Acceptance criteria (T-020):
  - pytest passes with 0 failures
  - Lane 1 and Lane 2 integration tests pass with mocked providers
  - Coverage target: pytest passes clean; all critical paths exercised
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.agents.a4_decision import A4DecisionAgent
from backend.agents.a5_notification import A5NotificationAgent
from backend.graph.state import ClaimState
from backend.main import app
from backend.ocr_provider.base import TagData
from backend.vision_provider.base import BrandResult, DamageResult


# ── Mock factory helpers ──────────────────────────────────────────────────────


def _make_damage_result(
    damage_types: list | None = None,
    severity_score: float = 0.3,
    confidence: float = 0.9,
) -> DamageResult:
    return DamageResult(
        damage_types=damage_types or ["cracked shell"],
        severity_score=severity_score,
        confidence=confidence,
    )


def _make_brand_result(
    brand: str = "Samsonite",
    is_luxury: bool = False,
    confidence: float = 0.9,
) -> BrandResult:
    return BrandResult(brand=brand, is_luxury=is_luxury, confidence=confidence)


def _make_tag_data(
    flight_number: str = "AI202",
    pnr: str = "ABC123",
    bag_id: str = "0572351234",
    confidence: float = 0.95,
) -> TagData:
    return TagData(
        flight_number=flight_number,
        pnr=pnr,
        bag_id=bag_id,
        confidence=confidence,
    )


def _make_db_mock(claim_count: int = 0) -> MagicMock:
    db = MagicMock()
    db.save_claim = AsyncMock(return_value=None)
    db.get_claim_count = AsyncMock(return_value=claim_count)
    db.get_recent_hashes = AsyncMock(return_value=[])
    db.update_claim_status = AsyncMock(return_value=None)
    return db


def _mock_all_providers(
    *,
    llm_reply: str = "Thank you, processing your claim.",
    damage_result: DamageResult | None = None,
    brand_result: BrandResult | None = None,
    tag_data: TagData | None = None,
    claim_count: int = 0,
):
    """
    Return a tuple of (patches, mocks_dict).
    Patches every provider factory in backend.dependencies — no real API calls.
    """
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value=llm_reply)

    mock_vision = MagicMock()
    mock_vision.analyze_damage = AsyncMock(
        return_value=damage_result or _make_damage_result()
    )
    mock_vision.classify_brand = AsyncMock(
        return_value=brand_result or _make_brand_result()
    )
    mock_vision.analyze_image = AsyncMock(return_value=MagicMock(
        is_bag=True,
        bag_confidence=0.95,
        damage_types=["cracked shell"],
        severity_score=0.3,
        damage_confidence=0.9,
        brand="Samsonite",
        is_luxury=False,
        brand_confidence=0.85,
        tag_visible=False,
        tag_confidence=0.0,
        raw_description="Standard Samsonite with cracked shell.",
        object_description="",
    ))

    mock_ocr = MagicMock()
    mock_ocr.extract_bag_tag = AsyncMock(return_value=tag_data or _make_tag_data())

    mock_db = _make_db_mock(claim_count=claim_count)
    mock_storage = MagicMock()
    mock_storage.save = AsyncMock(return_value="data/uploads/test.jpg")

    patches = (
        patch("backend.dependencies.provide_llm", return_value=mock_llm),
        patch("backend.dependencies.provide_vision", return_value=mock_vision),
        patch("backend.dependencies.provide_ocr", return_value=mock_ocr),
        patch("backend.dependencies.provide_db", return_value=mock_db),
        patch("backend.dependencies.provide_storage", return_value=mock_storage),
    )
    mocks = {
        "llm": mock_llm,
        "vision": mock_vision,
        "ocr": mock_ocr,
        "db": mock_db,
        "storage": mock_storage,
    }
    return patches, mocks


# ════════════════════════════════════════════════════════════════════════════════
# LANE 1 — Standard bag, auto-approve integration tests
# ════════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_lane1_webhook_returns_200():
    """
    Lane 1: POST /webhook with full image set → 200 OK.
    Standard bag ($60), non-luxury, no fraud — full pipeline mock.
    """
    patches, _ = _mock_all_providers(
        damage_result=_make_damage_result(severity_score=0.4),
        brand_result=_make_brand_result(is_luxury=False),
        tag_data=_make_tag_data(confidence=0.95),
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook",
                json={
                    "session_id": "t020-lane1-http",
                    "message": "confirm",
                    "image_paths": [
                        "uploads/t020/damage_front.jpg",
                        "uploads/t020/bag_tag.jpg",
                    ],
                    "conversation_step": "confirm",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["error"] is None


@pytest.mark.asyncio
async def test_lane1_direct_a4_routes_to_lane1():
    """
    Lane 1: Direct A4 invocation with standard-bag state.
    $60 compensation, non-luxury, no fraud → routing_lane must be 1.
    """
    state = ClaimState(
        session_id="t020-lane1-direct",
        image_paths=[
            "uploads/t020/damage_front.jpg",
            "uploads/t020/bag_tag.jpg",
        ],
        pnr="ABC123",
        bag_id="0572351234",
        flight_number="AI202",
        severity_score=0.4,
        compensation_estimate_usd=60.0,
        is_luxury=False,
        fraud_score=0.0,
        conversation_step="confirm",
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    result = await a4.handle(state, [])

    assert result.routing_lane == 1, "Standard $60 non-luxury bag must route to Lane 1"
    assert result.claim_id is not None
    assert result.claim_id.startswith("CLM-")
    assert result.error is None


@pytest.mark.asyncio
async def test_lane1_a5_issues_voucher():
    """
    Lane 1: A5 generates a VCH- voucher code and sets notification_sent=True.
    Must not set hitl_queued.
    """
    state = ClaimState(
        session_id="t020-lane1-voucher",
        claim_id="CLM-20260601-TEST",
        routing_lane=1,
        final_compensation_usd=60.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    db = _make_db_mock()
    a5 = A5NotificationAgent(db=db)
    result = await a5.handle(state, [])

    assert result.voucher_code is not None, "Lane 1 must produce a voucher code"
    assert result.voucher_code.startswith("VCH-"), (
        f"Expected VCH- prefix, got: {result.voucher_code}"
    )
    assert result.notification_sent is True
    assert result.hitl_queued is False, "Lane 1 must not set hitl_queued"


@pytest.mark.asyncio
async def test_lane1_full_pipeline_a4_then_a5():
    """
    Lane 1: Full sequential A4 → A5 pipeline on a single state object.
    Verifies that A4 output (routing_lane=1) feeds correctly into A5.
    """
    state = ClaimState(
        session_id="t020-lane1-pipeline",
        image_paths=[
            "uploads/t020/damage_01.jpg",
            "uploads/t020/bag_tag_01.jpg",
        ],
        pnr="XY1234",
        bag_id="9876543210",
        flight_number="AI303",
        severity_score=0.3,
        compensation_estimate_usd=45.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    db = _make_db_mock()

    # A4: routing decision
    a4 = A4DecisionAgent(db=db)
    state = await a4.handle(state, [])
    assert state.routing_lane == 1

    # A5: notification
    a5 = A5NotificationAgent(db=db)
    state = await a5.handle(state, [])

    assert state.voucher_code is not None
    assert state.voucher_code.startswith("VCH-")
    assert state.notification_sent is True
    assert state.hitl_queued is False


@pytest.mark.asyncio
async def test_lane1_db_save_called_once():
    """
    Lane 1: A4 calls db.save_claim() exactly once per handle() call.
    DB persistence is a side-effect that must fire on every routed claim.
    """
    state = ClaimState(
        session_id="t020-lane1-db",
        image_paths=[
            "uploads/t020/damage_01.jpg",
            "uploads/t020/bag_tag_01.jpg",
        ],
        pnr="XY9988",
        bag_id="1234567890",
        flight_number="AI303",
        severity_score=0.3,
        compensation_estimate_usd=45.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    await a4.handle(state, [])

    db.save_claim.assert_called_once()
    saved = db.save_claim.call_args[0][0]
    assert saved["pnr"] == "XY9988"
    assert saved["routing_lane"] == 1


# ════════════════════════════════════════════════════════════════════════════════
# LANE 2 — Luxury bag / high value → staff review integration tests
# ════════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_lane2_luxury_bag_webhook_returns_200():
    """
    Lane 2: POST /webhook with luxury-bag context → 200 OK.
    All providers mocked — no real API calls.
    """
    patches, _ = _mock_all_providers(
        damage_result=_make_damage_result(severity_score=0.3),
        brand_result=_make_brand_result(brand="Rimowa", is_luxury=True),
        tag_data=_make_tag_data(confidence=0.95),
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook",
                json={
                    "session_id": "t020-lane2-http",
                    "message": "confirm",
                    "image_paths": [
                        "uploads/t020/damage_luxury.jpg",
                        "uploads/t020/bag_tag.jpg",
                    ],
                    "conversation_step": "confirm",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["error"] is None


@pytest.mark.asyncio
async def test_lane2_luxury_bag_direct_a4_routes_to_lane2():
    """
    Lane 2: Direct A4 invocation with luxury-bag state.
    Luxury bag (Rimowa) with $40 compensation → routing_lane must be 2.
    """
    state = ClaimState(
        session_id="t020-lane2-direct",
        image_paths=[
            "uploads/t020/damage_luxury.jpg",
            "uploads/t020/bag_tag.jpg",
        ],
        pnr="LUX001",
        bag_id="9876543210",
        flight_number="AI404",
        severity_score=0.3,
        compensation_estimate_usd=40.0,
        is_luxury=True,
        brand_detected="Rimowa",
        fraud_score=0.0,
        conversation_step="confirm",
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    result = await a4.handle(state, [])

    assert result.routing_lane == 2, "Luxury bag must always route to Lane 2"
    assert result.claim_id is not None
    assert result.error is None


@pytest.mark.asyncio
async def test_lane2_a5_queues_for_hitl_review():
    """
    Lane 2: A5 sets hitl_queued=True and must NOT issue a voucher.
    Claim goes to staff review queue.
    """
    state = ClaimState(
        session_id="t020-lane2-hitl",
        claim_id="CLM-20260601-LXRY",
        routing_lane=2,
        final_compensation_usd=120.0,
        is_luxury=True,
        brand_detected="Rimowa",
        fraud_score=0.0,
    )

    db = _make_db_mock()
    a5 = A5NotificationAgent(db=db)
    result = await a5.handle(state, [])

    assert result.hitl_queued is True, "Lane 2 must queue claim for HITL review"
    assert result.voucher_code is None, "Lane 2 must NOT issue a voucher"


@pytest.mark.asyncio
async def test_lane2_high_value_routes_to_lane2():
    """
    Lane 2: High compensation ($200) with non-luxury standard bag.
    Value alone must route to Lane 2.
    """
    state = ClaimState(
        session_id="t020-lane2-highval",
        image_paths=[
            "uploads/t020/damage_expensive.jpg",
            "uploads/t020/bag_tag.jpg",
        ],
        pnr="HV1234",
        bag_id="1234567890",
        flight_number="AI505",
        severity_score=0.8,
        compensation_estimate_usd=200.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    result = await a4.handle(state, [])

    assert result.routing_lane == 2, "High-value claim must route to Lane 2"


@pytest.mark.asyncio
async def test_lane2_full_pipeline_a4_then_a5():
    """
    Lane 2: Full sequential A4 → A5 pipeline on a single state object.
    Luxury bag — verifies A4 → Lane 2 output feeds correctly into A5.
    """
    state = ClaimState(
        session_id="t020-lane2-pipeline",
        image_paths=[
            "uploads/t020/damage_luxury_01.jpg",
            "uploads/t020/bag_tag_luxury.jpg",
        ],
        pnr="LX5678",
        bag_id="0000000001",
        flight_number="AI606",
        severity_score=0.4,
        compensation_estimate_usd=60.0,
        is_luxury=True,
        brand_detected="Tumi",
        fraud_score=0.0,
    )

    db = _make_db_mock()

    # A4: routing decision
    a4 = A4DecisionAgent(db=db)
    state = await a4.handle(state, [])
    assert state.routing_lane == 2, "Tumi (luxury) must route to Lane 2"

    # A5: HITL queue
    a5 = A5NotificationAgent(db=db)
    state = await a5.handle(state, [])

    assert state.hitl_queued is True
    assert state.voucher_code is None


@pytest.mark.asyncio
async def test_lane2_db_update_claim_status_called():
    """
    Lane 2: A5 calls db.update_claim_status() to mark claim as AWAITING_REVIEW.
    """
    state = ClaimState(
        session_id="t020-lane2-db-status",
        claim_id="CLM-20260601-S2",
        routing_lane=2,
        final_compensation_usd=120.0,
    )

    db = _make_db_mock()
    a5 = A5NotificationAgent(db=db)
    await a5.handle(state, [])

    db.update_claim_status.assert_called_once()


# ════════════════════════════════════════════════════════════════════════════════
# RETRY / BLURRY IMAGE — guard behaviour
# ════════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_retry_blurry_tag_blocks_a4():
    """
    Retry scenario: A3 sets re_request_tag=True on blurry tag image.
    A4 guard must skip routing — routing_lane stays None.
    """
    state = ClaimState(
        session_id="t020-retry-blurry-tag",
        image_paths=[
            "uploads/t020/damage_front.jpg",
            "uploads/t020/bag_tag_blurry.jpg",
        ],
        pnr=None,
        bag_id=None,
        ocr_confidence=0.3,
        re_request_tag=True,  # A3 set this — tag was too blurry
        severity_score=0.4,
        compensation_estimate_usd=60.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    result = await a4.handle(state, [])

    assert result.routing_lane is None, (
        "A4 must not route when re_request_tag=True"
    )
    db.save_claim.assert_not_called()


@pytest.mark.asyncio
async def test_retry_blurry_damage_blocks_a4():
    """
    Retry scenario: A2 sets re_request_damage=True.
    A4 guard must skip routing — routing_lane stays None.
    """
    state = ClaimState(
        session_id="t020-retry-blurry-damage",
        image_paths=[
            "uploads/t020/damage_blurry.jpg",
            "uploads/t020/bag_tag.jpg",
        ],
        pnr="ABC123",
        bag_id="1234567890",
        re_request_damage=True,  # A2 set this — damage photos too blurry
        severity_score=0.0,
        compensation_estimate_usd=0.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    result = await a4.handle(state, [])

    assert result.routing_lane is None, (
        "A4 must not route when re_request_damage=True"
    )
    db.save_claim.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════════
# ERROR RESILIENCE
# ════════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_db_failure_does_not_prevent_routing():
    """
    DB failure (Supabase unreachable) must not block the routing decision.
    A4 should still set routing_lane and claim_id; error field stays None.
    """
    db = _make_db_mock()
    db.save_claim = AsyncMock(side_effect=Exception("Supabase connection refused"))
    db.get_claim_count = AsyncMock(return_value=0)
    db.get_recent_hashes = AsyncMock(return_value=[])

    state = ClaimState(
        session_id="t020-db-failure",
        image_paths=[
            "uploads/t020/damage_front.jpg",
            "uploads/t020/bag_tag.jpg",
        ],
        pnr="ABC123",
        bag_id="0572351234",
        flight_number="AI202",
        severity_score=0.3,
        compensation_estimate_usd=60.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    a4 = A4DecisionAgent(db=db)
    result = await a4.handle(state, [])

    # DB failed but routing must still complete
    assert result.routing_lane is not None, "Routing lane must be set even when DB fails"
    assert result.claim_id is not None, "Claim ID must be generated even when DB fails"
    assert result.error is None, (
        "DB failure must not set state.error (best-effort persistence)"
    )


@pytest.mark.asyncio
async def test_webhook_never_500_on_llm_failure():
    """
    Webhook resilience: LLM failure → 200 response with error field set.
    Server must stay up even when the LLM provider throws.
    """
    broken_llm = MagicMock()
    broken_llm.chat = AsyncMock(side_effect=Exception("Gemini API unavailable"))
    patches, _ = _mock_all_providers()

    # Overwrite the LLM mock with the broken one
    broken_patches = (
        patch("backend.dependencies.provide_llm", return_value=broken_llm),
        patches[1],
        patches[2],
        patches[3],
        patches[4],
    )
    with broken_patches[0], broken_patches[1], broken_patches[2], broken_patches[3], broken_patches[4]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook",
                json={
                    "session_id": "t020-llm-failure",
                    "message": "my bag is damaged",
                },
            )

    assert response.status_code == 200, "Server must never return 500"
    data = response.json()
    assert data["error"] is not None, "Error must be surfaced in response body"


@pytest.mark.asyncio
async def test_webhook_invalid_payload_returns_422():
    """
    Webhook validation: missing required field → 422 Unprocessable Entity.
    Pydantic schema validation must reject bad requests before they hit the graph.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/webhook",
            json={"message": "missing session_id"},  # session_id intentionally absent
        )

    assert response.status_code == 422


# ════════════════════════════════════════════════════════════════════════════════
# SESSION ISOLATION
# ════════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_two_sessions_are_independent():
    """
    Two concurrent passengers must have independent state.
    No cross-session state contamination via MemorySaver.
    """
    patches, _ = _mock_all_providers()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r_alice = await client.post(
                "/webhook",
                json={"session_id": "passenger-alice-t020", "message": "my bag is cracked"},
            )
            r_bob = await client.post(
                "/webhook",
                json={"session_id": "passenger-bob-t020", "message": "my suitcase broke"},
            )

    assert r_alice.status_code == 200
    assert r_bob.status_code == 200
    assert r_alice.json()["session_id"] == "passenger-alice-t020"
    assert r_bob.json()["session_id"] == "passenger-bob-t020"