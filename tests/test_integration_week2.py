"""
Week 2 Integration Tests — T-016.

Tests the full 5-agent pipeline end-to-end:
  Scenario A — Standard bag → Lane 1 auto-approve
  Scenario B — Luxury bag  → Lane 2 staff review
  Scenario C — Blurry images → retry prompts; A4 must NOT run

All provider calls are mocked — no API keys or real DB needed.
Uses httpx.AsyncClient with ASGITransport to call the real FastAPI app,
plus direct agent invocations to verify intra-agent guard logic.

Acceptance criteria (T-016):
  - Lane 1 claim completes; voucher_code set.
  - Lane 2 claim goes to review queue; hitl_queued = True.
  - Retry prompt triggered on blurry tag / blurry damage photos.
  - pytest → 0 failures.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.agents.a4_decision import A4DecisionAgent
from backend.graph.state import ClaimState
from backend.main import app
from backend.ocr_provider.base import TagData
from backend.vision_provider.base import BrandResult, DamageResult

# ── Mock helpers ──────────────────────────────────────────────────────────────


def _make_damage_result(
    damage_types=None,
    severity_score=0.3,
    confidence=0.9,
) -> DamageResult:
    return DamageResult(
        damage_types=damage_types or ["cracked shell"],
        severity_score=severity_score,
        confidence=confidence,
    )


def _make_brand_result(
    brand="Samsonite", is_luxury=False, confidence=0.9
) -> BrandResult:
    return BrandResult(brand=brand, is_luxury=is_luxury, confidence=confidence)


def _make_tag_data(
    flight_number="AI202",
    pnr="ABC123",
    bag_id="0572351234",
    confidence=0.95,
) -> TagData:
    return TagData(
        flight_number=flight_number,
        pnr=pnr,
        bag_id=bag_id,
        confidence=confidence,
    )


def _mock_providers(
    *,
    llm_reply: str = "Thank you, processing your claim.",
    damage_result: DamageResult | None = None,
    brand_result: BrandResult | None = None,
    tag_data: TagData | None = None,
    claim_count: int = 0,
):
    """
    Return a tuple of (context-manager patches, mock_objects_dict).

    Patches every provider factory in backend.dependencies so no real
    API call or DB connection is made during tests.
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

    mock_ocr = MagicMock()
    mock_ocr.extract_bag_tag = AsyncMock(return_value=tag_data or _make_tag_data())

    mock_db = MagicMock()
    mock_db.save_claim = AsyncMock(return_value=None)
    mock_db.get_claim_count = AsyncMock(return_value=claim_count)
    mock_db.get_recent_hashes = AsyncMock(return_value=[])
    mock_db.update_claim_status = AsyncMock(return_value=None)

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


def _make_db_mock(claim_count: int = 0) -> MagicMock:
    db = MagicMock()
    db.save_claim = AsyncMock(return_value=None)
    db.get_claim_count = AsyncMock(return_value=claim_count)
    db.get_recent_hashes = AsyncMock(return_value=[])
    db.update_claim_status = AsyncMock(return_value=None)
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO A — Standard bag → Lane 1 auto-approve
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_scenario_a_lane1_webhook_returns_200():
    """
    Scenario A (Lane 1): POST /webhook with full image set (damage + tag).
    Standard bag ($60), no fraud → pipeline completes with 200 OK.
    """
    patches, _ = _mock_providers(
        damage_result=_make_damage_result(severity_score=0.4),  # $60 → Lane 1
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
                    "session_id": "t016-scenario-a",
                    "message": "confirm",
                    "image_paths": [
                        "uploads/t016-a/damage_front.jpg",
                        "uploads/t016-a/bag_tag.jpg",
                    ],
                    "conversation_step": "confirm",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["error"] is None


@pytest.mark.asyncio
async def test_scenario_a_lane1_routing_and_voucher():
    """
    Scenario A (Lane 1): A4 routes to Lane 1; A5 generates a VCH- voucher.
    Standard bag, compensation $60 (below $100 threshold), no fraud.
    """
    from backend.agents.a2_vision import A2VisionAgent
    from backend.agents.a3_ocr import A3OCRAgent
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.agents.a5_notification import A5NotificationAgent

    state = ClaimState(
        session_id="t016-a-direct",
        image_paths=[
            "uploads/t016-a/damage_front.jpg",
            "uploads/t016-a/bag_tag.jpg",
        ],
        conversation_step="confirm",
        severity_score=0.4,
        compensation_estimate_usd=60.0,  # below $100 threshold → Lane 1
        is_luxury=False,
        fraud_score=0.0,
        pnr="ABC123",
        bag_id="0572351234",
        flight_number="AI202",
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    state = await a4.handle(state, [])

    assert state.routing_lane == 1, "Standard $60 bag should route to Lane 1"
    assert state.claim_id is not None
    assert state.claim_id.startswith("CLM-")

    a5 = A5NotificationAgent(db=db)
    state = await a5.handle(state, [])

    assert state.voucher_code is not None
    assert state.voucher_code.startswith("VCH-")
    assert state.notification_sent is True


@pytest.mark.asyncio
async def test_scenario_a_lane1_db_saved():
    """
    Scenario A (Lane 1): After A4 runs, save_claim is called exactly once.
    Verifies DB write happens on every Lane 1 decision.
    """
    state = ClaimState(
        session_id="t016-a-db",
        image_paths=[
            "uploads/t016-a/damage_01.jpg",
            "uploads/t016-a/bag_tag_01.jpg",
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


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO B — Luxury bag → Lane 2 staff review
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_scenario_b_lane2_luxury_bag_routing():
    """
    Scenario B (Lane 2): Luxury bag → A4 always routes to Lane 2,
    regardless of severity score.
    """
    state = ClaimState(
        session_id="t016-b-luxury",
        image_paths=[
            "uploads/t016-b/damage_luxury.jpg",
            "uploads/t016-b/bag_tag.jpg",
        ],
        pnr="LUX001",
        bag_id="9876543210",
        flight_number="AI404",
        severity_score=0.3,
        compensation_estimate_usd=45.0,  # would be Lane 1 without luxury flag
        is_luxury=True,  # luxury flag → always Lane 2
        fraud_score=0.0,
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    result = await a4.handle(state, [])

    assert result.routing_lane == 2, "Luxury bag must always route to Lane 2"
    assert result.claim_id is not None


@pytest.mark.asyncio
async def test_scenario_b_lane2_hitl_queued():
    """
    Scenario B (Lane 2): A5 sets hitl_queued = True and does NOT issue a voucher.
    Claim must go to HITL queue for staff review, not auto-approved.
    """
    from backend.agents.a5_notification import A5NotificationAgent

    state = ClaimState(
        session_id="t016-b-hitl",
        claim_id="CLM-20260526-TEST",
        routing_lane=2,
        final_compensation_usd=120.0,
        is_luxury=True,
        fraud_score=0.0,
    )

    db = _make_db_mock()
    a5 = A5NotificationAgent(db=db)
    result = await a5.handle(state, [])

    assert result.hitl_queued is True, "Lane 2 claim must be queued for staff review"
    assert result.voucher_code is None, "Lane 2 must NOT issue a voucher"


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO C — Blurry images → retry; A4 must NOT run
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_scenario_c_retry_blurry_tag_photo():
    """
    Scenario C — Blurry tag photo:
    A3 sets re_request_tag = True (low OCR confidence).
    A4 must NOT run — routing_lane must remain None.

    Previously failing: A4 guard only checked for missing image types,
    not for quality-retry flags. Fix: A4 now skips when re_request_tag is set.
    """
    state = ClaimState(
        session_id="t016-c-blurry-tag",
        image_paths=[
            "uploads/t016-c/damage_front.jpg",
            "uploads/t016-c/bag_tag_blurry.jpg",  # tag present but will fail OCR
        ],
        pnr=None,  # A3 could not extract — blurry
        bag_id=None,
        flight_number=None,
        ocr_confidence=0.3,  # below threshold
        re_request_tag=True,  # A3 set this flag
        severity_score=0.4,
        compensation_estimate_usd=60.0,
        is_luxury=False,
        fraud_score=0.0,
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    result = await a4.handle(state, [])

    assert (
        result.routing_lane is None
    ), "A4 should not run when tag is blurry — re_request_tag=True must block A4"
    db.save_claim.assert_not_called()


@pytest.mark.asyncio
async def test_scenario_c_retry_blurry_damage_photos():
    """
    Scenario C — Blurry damage photos:
    A2 sets re_request_damage = True (all damage photos below confidence threshold).
    A4 must NOT run — routing_lane must remain None.

    Previously failing: A4 guard did not check re_request_damage.
    Fix: A4 now skips when re_request_damage is set.
    """
    state = ClaimState(
        session_id="t016-c-blurry-damage",
        image_paths=[
            "uploads/t016-c/damage_blurry.jpg",  # present but too blurry for A2
            "uploads/t016-c/bag_tag_clear.jpg",
        ],
        re_request_damage=True,  # A2 set this flag — damage photos rejected
        re_request_tag=False,
        severity_score=0.0,  # A2 could not score — blurry
        compensation_estimate_usd=0.0,
        is_luxury=False,
        fraud_score=0.0,
        pnr="ABC123",
        bag_id="0572351234",
        flight_number="AI202",
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    result = await a4.handle(state, [])

    assert result.routing_lane is None, (
        "A4 should not run when damage photos are blurry — "
        "re_request_damage=True must block A4"
    )
    db.save_claim.assert_not_called()


@pytest.mark.asyncio
async def test_scenario_c_retry_flags_cleared_on_resubmit():
    """
    Scenario C — After passenger retakes photos:
    If re_request_tag/re_request_damage are both False, A4 runs normally.
    This verifies the guard is off on a clean retry submission.
    """
    state = ClaimState(
        session_id="t016-c-clean-retry",
        image_paths=[
            "uploads/t016-c/damage_clear.jpg",
            "uploads/t016-c/bag_tag_clear.jpg",
        ],
        re_request_tag=False,  # cleared — passenger retook photos
        re_request_damage=False,
        severity_score=0.4,
        compensation_estimate_usd=60.0,
        is_luxury=False,
        fraud_score=0.0,
        pnr="ABC123",
        bag_id="0572351234",
        flight_number="AI202",
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    result = await a4.handle(state, [])

    assert result.routing_lane in (
        1,
        2,
    ), "After clean retry, A4 should run and set routing_lane"
    assert result.claim_id is not None


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE — Full 5-agent end-to-end smoke tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_full_pipeline_lane1_smoke():
    """
    Full pipeline smoke test — Lane 1 path (direct agent calls, all mocked).

    Runs A2 → A3 → A4 → A5 in sequence and checks the final state has:
      - routing_lane == 1
      - voucher_code set
      - no error
    """
    from backend.agents.a2_vision import A2VisionAgent
    from backend.agents.a3_ocr import A3OCRAgent
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.agents.a5_notification import A5NotificationAgent

    state = ClaimState(
        session_id="t016-pipeline-lane1",
        image_paths=[
            "uploads/smoke/damage_wheel.jpg",
            "uploads/smoke/bag_tag_01.jpg",
        ],
        conversation_step="confirm",
        pnr="SMK001",
    )

    # A2 — mocked vision
    mock_vision = MagicMock()
    mock_vision.analyze_damage = AsyncMock(
        return_value=_make_damage_result(severity_score=0.35, confidence=0.9)
    )
    mock_vision.classify_brand = AsyncMock(
        return_value=_make_brand_result(is_luxury=False)
    )
    a2 = A2VisionAgent(vision=mock_vision)
    state = await a2.handle(state, [])

    # A3 — mocked OCR
    mock_ocr = MagicMock()
    mock_ocr.extract_bag_tag = AsyncMock(return_value=_make_tag_data(confidence=0.95))
    a3 = A3OCRAgent(ocr=mock_ocr)
    state = await a3.handle(state, [])

    assert state.re_request_tag is False
    assert state.re_request_damage is False

    # A4
    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    state = await a4.handle(state, [])

    assert state.routing_lane == 1

    # A5
    a5 = A5NotificationAgent(db=db)
    state = await a5.handle(state, [])

    assert state.voucher_code is not None
    assert state.voucher_code.startswith("VCH-")
    assert state.error is None


@pytest.mark.asyncio
async def test_full_pipeline_lane2_smoke():
    """
    Full pipeline smoke test — Lane 2 path (high value → staff review).

    A4 routes to Lane 2 when compensation exceeds $100 threshold.
    A5 sets hitl_queued and does not issue a voucher.
    """
    from backend.agents.a5_notification import A5NotificationAgent

    state = ClaimState(
        session_id="t016-pipeline-lane2",
        image_paths=[
            "uploads/smoke/damage_heavy.jpg",
            "uploads/smoke/bag_tag_02.jpg",
        ],
        severity_score=0.8,
        compensation_estimate_usd=120.0,  # > $100 → Lane 2
        is_luxury=False,
        fraud_score=0.0,
        pnr="SMK002",
        bag_id="1111111111",
        flight_number="AI505",
    )

    db = _make_db_mock()
    a4 = A4DecisionAgent(db=db)
    state = await a4.handle(state, [])

    assert state.routing_lane == 2

    a5 = A5NotificationAgent(db=db)
    state = await a5.handle(state, [])

    assert state.hitl_queued is True
    assert state.voucher_code is None
    assert state.error is None
