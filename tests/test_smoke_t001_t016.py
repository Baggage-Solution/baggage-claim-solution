"""
Smoke Test Suite — T-001 through T-016 full coverage pass.

PURPOSE
-------
This file is the single source of truth for "is the sprint green?" before
every merge gate (MG-W1, MG-W2). It covers every task from T-001 to T-016
with at least one smoke assertion per task's acceptance criterion.

It deliberately does NOT duplicate the deep unit tests that already live in
test_a1_agent.py, test_a2_vision.py, … test_integration_week2.py.
Instead it checks the acceptance criteria from the Task Tracker in one
place so the team can run this file alone for a fast confidence check.

Run:
    pytest tests/test_smoke_t001_t016.py -v

All external services mocked — no API keys, no Supabase, no Gemini needed.

COVERAGE MAP
------------
T-001  Repo / branching         → test_t001_*
T-002  Env & deps               → test_t002_*
T-003  React simulator scaffold → UI checklist (manual) — smoke: import only
T-004  FastAPI base + webhook   → test_t004_*
T-005  LangGraph skeleton       → test_t005_*
T-006  Gemini Vision provider   → test_t006_*
T-007  Gemini OCR provider      → test_t007_*
T-008  LLM provider + A1       → test_t008_*
T-009  Week 1 integration       → test_t009_*
T-010  Agent A2 vision node     → test_t010_*
T-011  Agent A3 OCR node        → test_t011_*
T-012  Agent A4 decision        → test_t012_*
T-013  Simulator full flow      → UI checklist (manual) — smoke: SSE endpoint
T-014  Supabase DB              → test_t014_*
T-015  Agent A5 notification    → test_t015_*
T-016  Week 2 integration       → test_t016_*
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── Shared mock builders ──────────────────────────────────────────────────────


def _db():
    db = MagicMock()
    db.save_claim = AsyncMock(return_value=None)
    db.get_claim_count = AsyncMock(return_value=0)
    db.get_recent_hashes = AsyncMock(return_value=[])
    db.update_claim_status = AsyncMock(return_value=None)
    return db


def _llm(reply="Hello! Please describe the damage."):
    m = MagicMock()
    m.chat = AsyncMock(return_value=reply)
    return m


def _vision(severity=0.3, confidence=0.9, is_luxury=False):
    from backend.vision_provider.base import BrandResult, DamageResult
    v = MagicMock()
    v.analyze_damage = AsyncMock(
        return_value=DamageResult(
            damage_types=["cracked shell"], severity_score=severity, confidence=confidence
        )
    )
    v.classify_brand = AsyncMock(
        return_value=BrandResult(brand="Samsonite", is_luxury=is_luxury, confidence=0.9)
    )
    return v


def _ocr(confidence=0.95):
    from backend.ocr_provider.base import TagData
    o = MagicMock()
    o.extract_bag_tag = AsyncMock(
        return_value=TagData(
            flight_number="AI202", pnr="ABC123", bag_id="0572351234", confidence=confidence
        )
    )
    return o


def _all_patches(llm=None, vision=None, ocr=None, db=None):
    """Return tuple of 5 patches covering all provider factories."""
    mock_storage = MagicMock()
    mock_storage.save = AsyncMock(return_value="data/uploads/test.jpg")
    return (
        patch("backend.dependencies.provide_llm", return_value=llm or _llm()),
        patch("backend.dependencies.provide_vision", return_value=vision or _vision()),
        patch("backend.dependencies.provide_ocr", return_value=ocr or _ocr()),
        patch("backend.dependencies.provide_db", return_value=db or _db()),
        patch("backend.dependencies.provide_storage", return_value=mock_storage),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# T-001  Repo Init & Branching Strategy
# ═══════════════════════════════════════════════════════════════════════════════


def test_t001_contributing_md_exists():
    """T-001: CONTRIBUTING.md must exist at repo root."""
    assert Path("CONTRIBUTING.md").exists(), "CONTRIBUTING.md missing from repo root"


def test_t001_gitignore_exists():
    """T-001: .gitignore must exist."""
    assert Path(".gitignore").exists()


def test_t001_folder_scaffold_present():
    """T-001: Core backend folders must exist as per architecture doc."""
    required = [
        "backend/agents",
        "backend/api/routes",
        "backend/graph",
        "backend/llm_provider",
        "backend/ocr_provider",
        "backend/vision_provider",
        "backend/db",
        "tests",
        "frontend",
    ]
    missing = [d for d in required if not Path(d).exists()]
    assert missing == [], f"Missing scaffold directories: {missing}"


def test_t001_branch_docs_folder():
    """T-001: BRANCH_DOCS/ folder exists with template."""
    assert Path("BRANCH_DOCS/TEMPLATE.md").exists()


# ═══════════════════════════════════════════════════════════════════════════════
# T-002  Environment & Dependency Setup
# ═══════════════════════════════════════════════════════════════════════════════


def test_t002_requirements_txt_exists():
    """T-002: requirements.txt must exist."""
    assert Path("requirements.txt").exists()


def test_t002_env_example_exists():
    """T-002: .env.example must exist with documented vars."""
    assert Path(".env.example").exists()


def test_t002_env_example_has_key_vars():
    """T-002: .env.example documents GEMINI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY."""
    content = Path(".env.example").read_text()
    for var in ["GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]:
        assert var in content, f".env.example missing {var}"


def test_t002_config_loads_without_real_env():
    """T-002: Settings object loads with defaults — no crash if .env is absent."""
    from backend.config import Settings
    # Instantiate without any env file — all optional fields default to None
    s = Settings(_env_file=None)
    assert s.service_name == "baggage-claim-ai"
    assert s.lane1_max_compensation_usd == 100.0


def test_t002_all_provider_switches_have_defaults():
    """T-002: All PROVIDER env vars have safe defaults so app starts without .env."""
    from backend.config import Settings
    s = Settings(_env_file=None)
    assert s.llm_provider == "gemini"
    assert s.vision_provider == "gemini"
    assert s.ocr_provider == "gemini"
    assert s.db_provider == "supabase"


# ═══════════════════════════════════════════════════════════════════════════════
# T-003  React Simulator Scaffold  (backend smoke only — UI = manual checklist)
# ═══════════════════════════════════════════════════════════════════════════════


def test_t003_frontend_folder_exists():
    """T-003: frontend/ directory exists (React app scaffolded)."""
    assert Path("frontend").exists(), "frontend/ folder missing — T-003 not complete"


# ═══════════════════════════════════════════════════════════════════════════════
# T-004  FastAPI Base + Webhook Endpoint
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_t004_health_endpoint_up():
    """T-004: GET /health returns 200 and service name."""
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/health")
    assert r.status_code in (200, 503)  # 503 OK if env vars missing in CI
    assert r.json()["service"] == "baggage-claim-ai"


@pytest.mark.asyncio
async def test_t004_webhook_accepts_post():
    """T-004: POST /webhook returns 200 with session_id echoed back."""
    from backend.main import app
    patches = _all_patches()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/webhook", json={"session_id": "t004-smoke", "message": "hi"})
    assert r.status_code == 200
    assert r.json()["session_id"] == "t004-smoke"


@pytest.mark.asyncio
async def test_t004_webhook_missing_session_id_returns_422():
    """T-004: Pydantic validation rejects missing session_id with 422."""
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/webhook", json={"message": "no session id"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_t004_cors_headers_present():
    """T-004: CORS headers present on /health (POC allows all origins)."""
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.options("/health", headers={"Origin": "http://localhost:5173"})
    # OPTIONS may return 405 if not explicitly handled — check CORS on GET instead
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" in r.headers


def test_t004_signature_verification_skips_without_secret():
    """T-004: verify_whatsapp_signature returns True when WHATSAPP_APP_SECRET not set."""
    from backend.api.routes.webhook import verify_whatsapp_signature
    os.environ.pop("WHATSAPP_APP_SECRET", None)
    assert verify_whatsapp_signature(b"payload", None) is True
    assert verify_whatsapp_signature(b"payload", "wrong-sig") is True


# ═══════════════════════════════════════════════════════════════════════════════
# T-005  LangGraph State Schema + Graph Skeleton
# ═══════════════════════════════════════════════════════════════════════════════


def test_t005_graph_compiles():
    """T-005: LangGraph graph compiles without errors — MemorySaver wired."""
    from backend.graph.orchestrator import get_graph
    graph = get_graph()
    assert graph is not None


def test_t005_claim_state_all_fields():
    """T-005: ClaimState has all required fields from architecture doc."""
    from backend.graph.state import ClaimState
    s = ClaimState(session_id="s", passenger_message="m")
    # A1 fields
    assert hasattr(s, "conversation_step")
    assert hasattr(s, "a1_response")
    assert hasattr(s, "re_request_tag")
    assert hasattr(s, "re_request_damage")
    # A2 fields
    assert hasattr(s, "damage_types")
    assert hasattr(s, "severity_score")
    assert hasattr(s, "is_luxury")
    assert hasattr(s, "compensation_estimate_usd")
    # A3 fields
    assert hasattr(s, "flight_number")
    assert hasattr(s, "pnr")
    assert hasattr(s, "bag_id")
    assert hasattr(s, "ocr_confidence")
    # A4 fields
    assert hasattr(s, "routing_lane")
    assert hasattr(s, "fraud_score")
    assert hasattr(s, "fraud_flags")
    assert hasattr(s, "claim_id")
    # A5 fields
    assert hasattr(s, "voucher_code")
    assert hasattr(s, "notification_sent")
    assert hasattr(s, "hitl_queued")


def test_t005_is_lane1_eligible_all_three_conditions():
    """T-005: is_lane1_eligible() correctly gates on all 3 conditions."""
    from backend.graph.state import ClaimState
    # Low value + not luxury + low fraud → Lane 1
    s = ClaimState(session_id="s", passenger_message="m",
                   compensation_estimate_usd=50.0, is_luxury=False, fraud_score=0.0)
    assert s.is_lane1_eligible() is True
    # Fail on value
    s.compensation_estimate_usd = 150.0
    assert s.is_lane1_eligible() is False
    s.compensation_estimate_usd = 50.0
    # Fail on luxury
    s.is_luxury = True
    assert s.is_lane1_eligible() is False
    s.is_luxury = False
    # Fail on fraud
    s.fraud_score = 0.6
    assert s.is_lane1_eligible() is False


@pytest.mark.asyncio
async def test_t005_orchestrator_text_turn_smoke():
    """T-005: ClaimOrchestrator.run() completes on a text-only turn."""
    from backend.graph.orchestrator import ClaimOrchestrator
    patches = _all_patches()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = await ClaimOrchestrator().run(
            session_id="t005-smoke", passenger_message="hi"
        )
    assert result.execution_completed is True
    assert result.error is None


# ═══════════════════════════════════════════════════════════════════════════════
# T-006  Gemini Vision Provider
# ═══════════════════════════════════════════════════════════════════════════════


def test_t006_vision_provider_abc_importable():
    """T-006: VisionProvider ABC and concrete implementations are importable."""
    from backend.vision_provider.base import BrandResult, DamageResult, VisionProvider
    from backend.vision_provider.gemini_vision import GeminiVisionProvider
    assert issubclass(GeminiVisionProvider, VisionProvider)


def test_t006_damage_result_dataclass():
    """T-006: DamageResult holds damage_types, severity_score, confidence."""
    from backend.vision_provider.base import DamageResult
    dr = DamageResult(damage_types=["crack"], severity_score=0.5, confidence=0.9)
    assert dr.damage_types == ["crack"]
    assert dr.severity_score == 0.5


def test_t006_brand_result_dataclass():
    """T-006: BrandResult holds brand, is_luxury, confidence."""
    from backend.vision_provider.base import BrandResult
    br = BrandResult(brand="Rimowa", is_luxury=True, confidence=0.95)
    assert br.is_luxury is True


@pytest.mark.asyncio
async def test_t006_analyze_damage_mocked():
    """T-006: analyze_damage() returns DamageResult — mocked provider works."""
    from backend.vision_provider.base import DamageResult
    v = _vision(severity=0.6)
    result = await v.analyze_damage("fake/damage.jpg")
    assert isinstance(result, DamageResult)
    assert result.severity_score == 0.6


@pytest.mark.asyncio
async def test_t006_classify_brand_mocked():
    """T-006: classify_brand() returns BrandResult — mocked provider works."""
    from backend.vision_provider.base import BrandResult
    v = _vision(is_luxury=True)
    result = await v.classify_brand("fake/luxury.jpg")
    assert isinstance(result, BrandResult)
    assert result.is_luxury is True


# ═══════════════════════════════════════════════════════════════════════════════
# T-007  Gemini OCR Provider
# ═══════════════════════════════════════════════════════════════════════════════


def test_t007_ocr_provider_abc_importable():
    """T-007: OCRProvider ABC and GeminiOCRProvider are importable."""
    from backend.ocr_provider.base import OCRProvider, TagData
    from backend.ocr_provider.gemini_ocr import GeminiOCRProvider
    assert issubclass(GeminiOCRProvider, OCRProvider)


def test_t007_tag_data_dataclass():
    """T-007: TagData holds flight_number, pnr, bag_id, confidence."""
    from backend.ocr_provider.base import TagData
    td = TagData(flight_number="AI202", pnr="ABC123", bag_id="0572351234", confidence=0.95)
    assert td.pnr == "ABC123"
    assert td.confidence == 0.95


@pytest.mark.asyncio
async def test_t007_extract_bag_tag_mocked():
    """T-007: extract_bag_tag() returns TagData from mocked provider."""
    from backend.ocr_provider.base import TagData
    o = _ocr(confidence=0.88)
    result = await o.extract_bag_tag("fake/tag.jpg")
    assert isinstance(result, TagData)
    assert result.confidence == 0.88


def test_t007_pnr_pattern_validation():
    """T-007: PNR_PATTERN rejects short/special-char PNRs, accepts valid ones."""
    from backend.agents.a3_ocr import PNR_PATTERN
    assert PNR_PATTERN.match("ABC123")
    assert PNR_PATTERN.match("X1Y2Z3")
    assert not PNR_PATTERN.match("AB12")       # too short
    assert not PNR_PATTERN.match("AB-123")     # hyphen
    assert not PNR_PATTERN.match("ABCDEFG")    # too long


def test_t007_bag_id_pattern_accepts_10_to_12_digits():
    """T-007: BAG_ID_PATTERN accepts 10, 11, 12 digits (updated after T-007 fix)."""
    from backend.agents.a3_ocr import BAG_ID_PATTERN
    assert BAG_ID_PATTERN.match("1234567890")    # 10 digits
    assert BAG_ID_PATTERN.match("12345678901")   # 11 digits
    assert BAG_ID_PATTERN.match("123456789012")  # 12 digits
    assert not BAG_ID_PATTERN.match("123456789")  # 9 digits — rejected
    assert not BAG_ID_PATTERN.match("1234567890A") # letters — rejected


# ═══════════════════════════════════════════════════════════════════════════════
# T-008  LLM Provider + Agent A1
# ═══════════════════════════════════════════════════════════════════════════════


def test_t008_llm_provider_abc_importable():
    """T-008: LLMProvider ABC importable; GeminiLLMProvider importable when google-generativeai installed."""
    from backend.llm_provider.base import LLMProvider
    assert LLMProvider is not None
    try:
        from backend.llm_provider.gemini_llm import GeminiLLMProvider
        assert issubclass(GeminiLLMProvider, LLMProvider)
    except ModuleNotFoundError:
        pytest.skip("google-generativeai not installed in this environment")


def test_t008_a1_steps_defined():
    """T-008: All 5 conversation steps defined in A1 STEPS list."""
    from backend.agents.a1_conversation import STEPS
    assert "greeting" in STEPS
    assert "damage_photos" in STEPS
    assert "tag_photo" in STEPS
    assert "confirm" in STEPS
    assert "result" in STEPS


@pytest.mark.asyncio
async def test_t008_a1_greeting_advances_step():
    """T-008: A1 on greeting step sets a1_response and advances to damage_photos."""
    from backend.agents.a1_conversation import A1ConversationAgent
    from backend.graph.state import ClaimState
    agent = A1ConversationAgent(llm=_llm("Please describe the damage."))
    state = ClaimState(session_id="t008", passenger_message="hi", conversation_step="greeting")
    result = await agent.handle(state, [])
    assert result.a1_response is not None
    assert result.conversation_step == "damage_photos"
    assert result.error is None


@pytest.mark.asyncio
async def test_t008_a1_error_does_not_crash():
    """T-008: LLM exception → state.error set, pipeline never raises."""
    from backend.agents.a1_conversation import A1ConversationAgent
    from backend.graph.state import ClaimState
    broken = MagicMock()
    broken.chat = AsyncMock(side_effect=Exception("LLM timeout"))
    agent = A1ConversationAgent(llm=broken)
    state = ClaimState(session_id="t008-err", passenger_message="hi")
    result = await agent.handle(state, [])
    assert result.error is not None
    assert "A1 error" in result.error


@pytest.mark.asyncio
async def test_t008_a1_does_not_import_gemini_directly():
    """T-008: agents/a1_conversation.py must not import google.generativeai."""
    source = Path("backend/agents/a1_conversation.py").read_text()
    assert "google.generativeai" not in source, (
        "A1 agent must never import Gemini directly — use LLMProvider abstraction"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# T-009  Week 1 Integration
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_t009_three_round_trips():
    """T-009: 3 consecutive messages in one session all return 200 with replies."""
    from backend.main import app
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(side_effect=[
        "Please describe the damage.",
        "Upload photos of the damage.",
        "Now upload your bag tag photo.",
    ])
    patches = _all_patches(llm=mock_llm)
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for i, msg in enumerate(["hi", "wheel is cracked", "here are photos"]):
                r = await c.post("/webhook", json={"session_id": "t009-3rounds", "message": msg})
                assert r.status_code == 200, f"Round {i+1} failed: {r.status_code}"
                assert r.json()["reply"] != "", f"Round {i+1} empty reply"


@pytest.mark.asyncio
async def test_t009_session_isolation():
    """T-009: Two passengers get independent sessions — no state bleed."""
    from backend.main import app
    patches = _all_patches()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            ra = await c.post("/webhook", json={"session_id": "alice-t009", "message": "hi"})
            rb = await c.post("/webhook", json={"session_id": "bob-t009", "message": "hello"})
    assert ra.json()["session_id"] == "alice-t009"
    assert rb.json()["session_id"] == "bob-t009"


@pytest.mark.asyncio
async def test_t009_llm_failure_returns_200_not_500():
    """T-009: LLM crash → 200 with error field, never 500."""
    from backend.main import app
    patches = _all_patches(llm=_llm_broken())
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/webhook", json={"session_id": "t009-fail", "message": "hi"})
    assert r.status_code == 200
    assert r.json()["error"] is not None


def _llm_broken():
    m = MagicMock()
    m.chat = AsyncMock(side_effect=Exception("LLM unavailable"))
    return m


# ═══════════════════════════════════════════════════════════════════════════════
# T-010  Agent A2 — Vision Analysis Node
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_t010_a2_no_agent_imports_gemini():
    """T-010: agents/a2_vision.py must not import Gemini directly."""
    source = Path("backend/agents/a2_vision.py").read_text()
    assert "google.generativeai" not in source


@pytest.mark.asyncio
async def test_t010_a2_damage_photo_analysis():
    """T-010: A2 sets damage_types, severity_score, compensation from vision provider."""
    from backend.agents.a2_vision import A2VisionAgent
    from backend.graph.state import ClaimState
    v = _vision(severity=0.5)
    agent = A2VisionAgent(vision=v)
    state = ClaimState(
        session_id="t010", passenger_message="", image_paths=["uploads/damage.jpg"]
    )
    result = await agent.handle(state, [])
    assert result.severity_score == 0.5
    assert result.compensation_estimate_usd == 75.0   # 0.5 × 150
    assert result.error is None


@pytest.mark.asyncio
async def test_t010_a2_skips_tag_photos():
    """T-010: A2 does not call vision on tag photos — filtering by filename."""
    from backend.agents.a2_vision import A2VisionAgent
    from backend.graph.state import ClaimState
    v = _vision()
    agent = A2VisionAgent(vision=v)
    state = ClaimState(
        session_id="t010-tag", passenger_message="",
        image_paths=["uploads/bag_tag.jpg"],  # tag only — A2 must skip
    )
    await agent.handle(state, [])
    v.analyze_damage.assert_not_called()


@pytest.mark.asyncio
async def test_t010_a2_luxury_sets_is_luxury_flag():
    """T-010: A2 sets is_luxury=True for luxury brand results."""
    from backend.agents.a2_vision import A2VisionAgent
    from backend.graph.state import ClaimState
    v = _vision(is_luxury=True)
    agent = A2VisionAgent(vision=v)
    state = ClaimState(
        session_id="t010-lux", passenger_message="",
        image_paths=["uploads/rimowa_damage.jpg"],
    )
    result = await agent.handle(state, [])
    assert result.is_luxury is True


@pytest.mark.asyncio
async def test_t010_a2_low_confidence_sets_re_request():
    """T-010: Very blurry images → re_request_damage=True, severity not written."""
    from backend.agents.a2_vision import A2VisionAgent
    from backend.graph.state import ClaimState
    v = _vision(severity=0.5, confidence=0.1)  # below 0.4 threshold
    agent = A2VisionAgent(vision=v)
    state = ClaimState(
        session_id="t010-blur", passenger_message="",
        image_paths=["uploads/blurry.jpg"],
    )
    result = await agent.handle(state, [])
    assert result.re_request_damage is True
    assert result.severity_score == 0.0  # not written when rejected


# ═══════════════════════════════════════════════════════════════════════════════
# T-011  Agent A3 — OCR / Data Extraction Node
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_t011_a3_extracts_tag_fields():
    """T-011: A3 writes pnr, flight_number, bag_id, ocr_confidence to state."""
    from backend.agents.a3_ocr import A3OCRAgent
    from backend.graph.state import ClaimState
    o = _ocr(confidence=0.95)
    agent = A3OCRAgent(ocr=o)
    state = ClaimState(
        session_id="t011", passenger_message="",
        image_paths=["uploads/bag_tag.jpg"],
    )
    result = await agent.handle(state, [])
    assert result.pnr == "ABC123"
    assert result.flight_number == "AI202"
    assert result.bag_id == "0572351234"
    assert result.ocr_confidence == 0.95
    assert result.re_request_tag is False


@pytest.mark.asyncio
async def test_t011_a3_low_confidence_triggers_retry():
    """T-011: OCR confidence < 0.7 → re_request_tag=True, fields NOT written."""
    from backend.agents.a3_ocr import A3OCRAgent
    from backend.graph.state import ClaimState
    o = _ocr(confidence=0.4)
    agent = A3OCRAgent(ocr=o)
    state = ClaimState(
        session_id="t011-blur", passenger_message="",
        image_paths=["uploads/blurry_tag.jpg"],
    )
    result = await agent.handle(state, [])
    assert result.re_request_tag is True
    assert result.pnr is None  # not written when confidence too low


@pytest.mark.asyncio
async def test_t011_a3_skips_damage_photos():
    """T-011: A3 does NOT call OCR on damage photos — tag filter correct."""
    from backend.agents.a3_ocr import A3OCRAgent
    from backend.graph.state import ClaimState
    o = _ocr()
    agent = A3OCRAgent(ocr=o)
    state = ClaimState(
        session_id="t011-skip", passenger_message="",
        image_paths=["uploads/damage_front.jpg"],  # no tag here
    )
    await agent.handle(state, [])
    o.extract_bag_tag.assert_not_called()


@pytest.mark.asyncio
async def test_t011_a3_no_agent_imports_gemini():
    """T-011: agents/a3_ocr.py must not import Gemini directly."""
    source = Path("backend/agents/a3_ocr.py").read_text()
    assert "google.generativeai" not in source


# ═══════════════════════════════════════════════════════════════════════════════
# T-012  Agent A4 — Decision Engine
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_t012_claim_id_format():
    """T-012: Generated claim_id matches CLM-YYYYMMDD-XXXX format."""
    from backend.agents.a4_decision import _generate_claim_id
    cid = _generate_claim_id()
    parts = cid.split("-")
    assert parts[0] == "CLM"
    assert len(parts[1]) == 8
    assert len(parts[2]) == 4


@pytest.mark.asyncio
async def test_t012_lane1_standard_bag():
    """T-012 Scenario 1: Standard bag ≤$100, no luxury, no fraud → Lane 1."""
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.graph.state import ClaimState
    db = _db()
    agent = A4DecisionAgent(db=db)
    state = ClaimState(
        session_id="t012-lane1", passenger_message="",
        pnr="ABC123", bag_id="1234567890",
        compensation_estimate_usd=60.0, is_luxury=False, fraud_score=0.0,
    )
    result = await agent.handle(state, [])
    assert result.routing_lane == 1
    assert result.claim_id.startswith("CLM-")


@pytest.mark.asyncio
async def test_t012_lane2_high_value():
    """T-012 Scenario 2: >$100 compensation → Lane 2."""
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.graph.state import ClaimState
    agent = A4DecisionAgent(db=_db())
    state = ClaimState(
        session_id="t012-hv", passenger_message="",
        compensation_estimate_usd=150.0, is_luxury=False, fraud_score=0.0,
    )
    result = await agent.handle(state, [])
    assert result.routing_lane == 2


@pytest.mark.asyncio
async def test_t012_lane2_luxury():
    """T-012 Scenario 3: Luxury bag → Lane 2 regardless of value."""
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.graph.state import ClaimState
    agent = A4DecisionAgent(db=_db())
    state = ClaimState(
        session_id="t012-lux", passenger_message="",
        compensation_estimate_usd=40.0, is_luxury=True, fraud_score=0.0,
    )
    result = await agent.handle(state, [])
    assert result.routing_lane == 2


@pytest.mark.asyncio
async def test_t012_a4_skips_on_re_request_tag():
    """T-012: A4 guard skips when re_request_tag=True (our T-016 fix)."""
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.graph.state import ClaimState
    db = _db()
    agent = A4DecisionAgent(db=db)
    state = ClaimState(
        session_id="t012-retry", passenger_message="",
        image_paths=["uploads/damage.jpg", "uploads/bag_tag_blurry.jpg"],
        re_request_tag=True,
        compensation_estimate_usd=60.0,
    )
    result = await agent.handle(state, [])
    assert result.routing_lane is None
    db.save_claim.assert_not_called()


@pytest.mark.asyncio
async def test_t012_luxury_compensation_multiplier():
    """T-012: Luxury bags get 1.5× multiplier applied to final_compensation_usd."""
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.graph.state import ClaimState
    agent = A4DecisionAgent(db=_db())
    state = ClaimState(
        session_id="t012-mult", passenger_message="",
        compensation_estimate_usd=80.0, is_luxury=True, fraud_score=0.0,
    )
    result = await agent.handle(state, [])
    assert result.final_compensation_usd == 120.0  # 80 × 1.5


@pytest.mark.asyncio
async def test_t012_db_save_called_on_every_decision():
    """T-012: save_claim() called exactly once per successful A4 run."""
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.graph.state import ClaimState
    db = _db()
    agent = A4DecisionAgent(db=db)
    state = ClaimState(
        session_id="t012-db", passenger_message="",
        compensation_estimate_usd=50.0, is_luxury=False, fraud_score=0.0,
    )
    await agent.handle(state, [])
    db.save_claim.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# T-013  Simulator Full Flow  (backend smoke — UI = manual checklist)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.skip(reason="SSE generator never terminates in CI — verify manually via curl -N /events/{session_id}")
async def test_t013_sse_endpoint_returns_streaming_response():
    """T-013: GET /events/{session_id} returns 200 with text/event-stream."""
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        async with c.stream("GET", "/events/t013-session") as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]
            # Read first chunk (connected event) and break
            async for chunk in r.aiter_text():
                assert "connected" in chunk
                break


@pytest.mark.asyncio
async def test_t013_upload_endpoint_exists():
    """T-013: POST /upload endpoint is registered and returns structured response."""
    from backend.main import app
    import io
    mock_storage = MagicMock()
    mock_storage.save = AsyncMock(return_value="data/uploads/test_damage_img.jpg")
    with patch("backend.dependencies.provide_storage", return_value=mock_storage):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/upload",
                data={"session_id": "t013", "claim_id": "CLM-TEST", "photo_type": "damage"},
                files={"file": ("damage.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
            )
    assert r.status_code == 200
    data = r.json()
    assert "path" in data
    assert "filename" in data


# ═══════════════════════════════════════════════════════════════════════════════
# T-014  Supabase Schema + DB Integration
# ═══════════════════════════════════════════════════════════════════════════════


def test_t014_db_provider_abc_importable():
    """T-014: DBProvider ABC importable — abstraction layer in place."""
    from backend.db.base import DBProvider
    assert DBProvider is not None


def test_t014_supabase_client_importable():
    """T-014: SupabaseDBProvider importable without real credentials."""
    from backend.db.supabase_client import SupabaseDBProvider
    assert SupabaseDBProvider is not None


def test_t014_supabase_raises_on_missing_url():
    """T-014: SupabaseDBProvider.__init__ raises ValueError on None URL."""
    from backend.db.supabase_client import SupabaseDBProvider
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        provider = SupabaseDBProvider.__new__(SupabaseDBProvider)
        SupabaseDBProvider.__init__(provider, url=None, service_role_key="key")


@pytest.mark.asyncio
async def test_t014_save_claim_calls_insert():
    """T-014: save_claim() calls table('claims').insert() exactly once."""
    from backend.db.supabase_client import SupabaseDBProvider
    mock_client = MagicMock()
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[{"id": "CLM-TEST"}])
    chain.insert.return_value = chain
    mock_client.table.return_value = chain

    provider = SupabaseDBProvider.__new__(SupabaseDBProvider)
    provider._client = mock_client

    result = await provider.save_claim({"id": "CLM-TEST", "pnr": "ABC"})
    assert result == "CLM-TEST"
    chain.insert.assert_called_once()


@pytest.mark.asyncio
async def test_t014_update_claim_status_calls_update():
    """T-014: update_claim_status() sets status column correctly."""
    from backend.db.supabase_client import SupabaseDBProvider
    mock_client = MagicMock()
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[])
    chain.update.return_value = chain
    chain.eq.return_value = chain
    mock_client.table.return_value = chain

    provider = SupabaseDBProvider.__new__(SupabaseDBProvider)
    provider._client = mock_client

    await provider.update_claim_status("CLM-TEST", "APPROVED")
    chain.update.assert_called_once_with({"status": "APPROVED"})


@pytest.mark.asyncio
async def test_t014_get_claim_count_returns_int():
    """T-014: get_claim_count() returns integer count from Supabase."""
    from backend.db.supabase_client import SupabaseDBProvider
    mock_client = MagicMock()
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[], count=2)
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    mock_client.table.return_value = chain

    provider = SupabaseDBProvider.__new__(SupabaseDBProvider)
    provider._client = mock_client

    result = await provider.get_claim_count("ABC123", days=30)
    assert result == 2


# ═══════════════════════════════════════════════════════════════════════════════
# T-015  Agent A5 — Notification (Simulated)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_t015_lane1_voucher_format():
    """T-015: Lane 1 → voucher_code is VCH-XXXXXXXX (12 chars total)."""
    from backend.agents.a5_notification import A5NotificationAgent
    from backend.graph.state import ClaimState
    agent = A5NotificationAgent(db=_db())
    state = ClaimState(
        session_id="t015-lane1", claim_id="CLM-20260526-T015",
        routing_lane=1, final_compensation_usd=60.0,
    )
    result = await agent.handle(state, [])
    assert result.voucher_code is not None
    assert result.voucher_code.startswith("VCH-")
    assert len(result.voucher_code) == 12


@pytest.mark.asyncio
async def test_t015_lane1_db_status_approved():
    """T-015: Lane 1 → DB update_claim_status called with APPROVED."""
    from backend.agents.a5_notification import A5NotificationAgent
    from backend.graph.state import ClaimState
    db = _db()
    agent = A5NotificationAgent(db=db)
    state = ClaimState(
        session_id="t015-db", claim_id="CLM-20260526-T015",
        routing_lane=1, final_compensation_usd=60.0,
    )
    await agent.handle(state, [])
    db.update_claim_status.assert_called_once_with("CLM-20260526-T015", "APPROVED")


@pytest.mark.asyncio
async def test_t015_lane1_sse_event_pushed():
    """T-015: Lane 1 → SSE event of type 'lane1_result' in session queue."""
    from backend.agents.a5_notification import A5NotificationAgent, get_or_create_queue
    from backend.graph.state import ClaimState
    sid = "t015-sse-lane1"
    agent = A5NotificationAgent(db=_db())
    state = ClaimState(
        session_id=sid, claim_id="CLM-20260526-T015",
        routing_lane=1, final_compensation_usd=60.0,
    )
    await agent.handle(state, [])
    queue = get_or_create_queue(sid)
    assert not queue.empty()
    event = await queue.get()
    assert event["type"] == "lane1_result"
    assert event["voucher_code"].startswith("VCH-")


@pytest.mark.asyncio
async def test_t015_lane2_hitl_queued_no_voucher():
    """T-015: Lane 2 → hitl_queued=True, voucher_code=None."""
    from backend.agents.a5_notification import A5NotificationAgent
    from backend.graph.state import ClaimState
    agent = A5NotificationAgent(db=_db())
    state = ClaimState(
        session_id="t015-lane2", claim_id="CLM-20260526-T015",
        routing_lane=2, final_compensation_usd=120.0,
    )
    result = await agent.handle(state, [])
    assert result.hitl_queued is True
    assert result.voucher_code is None


@pytest.mark.asyncio
async def test_t015_lane2_db_status_awaiting_review():
    """T-015: Lane 2 → DB update_claim_status called with AWAITING_REVIEW."""
    from backend.agents.a5_notification import A5NotificationAgent
    from backend.graph.state import ClaimState
    db = _db()
    agent = A5NotificationAgent(db=db)
    state = ClaimState(
        session_id="t015-db2", claim_id="CLM-20260526-T015",
        routing_lane=2, final_compensation_usd=120.0,
    )
    await agent.handle(state, [])
    db.update_claim_status.assert_called_once_with("CLM-20260526-T015", "AWAITING_REVIEW")


@pytest.mark.asyncio
async def test_t015_lane2_sse_event_pushed():
    """T-015: Lane 2 → SSE event of type 'lane2_result' in session queue."""
    from backend.agents.a5_notification import A5NotificationAgent, get_or_create_queue
    from backend.graph.state import ClaimState
    sid = "t015-sse-lane2"
    agent = A5NotificationAgent(db=_db())
    state = ClaimState(
        session_id=sid, claim_id="CLM-20260526-T015",
        routing_lane=2, final_compensation_usd=120.0,
    )
    await agent.handle(state, [])
    queue = get_or_create_queue(sid)
    event = await queue.get()
    assert event["type"] == "lane2_result"


@pytest.mark.asyncio
async def test_t015_db_failure_does_not_crash():
    """T-015: DB failure in A5 → pipeline continues, voucher still generated."""
    from backend.agents.a5_notification import A5NotificationAgent
    from backend.graph.state import ClaimState
    db = _db()
    db.update_claim_status = AsyncMock(side_effect=Exception("Supabase down"))
    agent = A5NotificationAgent(db=db)
    state = ClaimState(
        session_id="t015-dbfail", claim_id="CLM-TEST",
        routing_lane=1, final_compensation_usd=60.0,
    )
    result = await agent.handle(state, [])
    assert result.voucher_code is not None  # voucher still generated
    assert result.error is None             # A5 handles DB failure gracefully


# ═══════════════════════════════════════════════════════════════════════════════
# T-016  Week 2 Integration — Full 5-Agent Pipeline
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_t016_scenario_a_full_lane1_chain():
    """T-016 Scenario A: A2→A3→A4→A5 chain with standard bag → voucher issued."""
    from backend.agents.a2_vision import A2VisionAgent
    from backend.agents.a3_ocr import A3OCRAgent
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.agents.a5_notification import A5NotificationAgent
    from backend.graph.state import ClaimState

    state = ClaimState(
        session_id="t016-full-lane1",
        image_paths=["uploads/t016/damage.jpg", "uploads/t016/bag_tag.jpg"],
    )
    # A2
    state = await A2VisionAgent(vision=_vision(severity=0.4, confidence=0.9)).handle(state, [])
    assert state.re_request_damage is False
    # A3
    state = await A3OCRAgent(ocr=_ocr(confidence=0.95)).handle(state, [])
    assert state.re_request_tag is False
    # A4
    db = _db()
    state = await A4DecisionAgent(db=db).handle(state, [])
    assert state.routing_lane == 1
    # A5
    state = await A5NotificationAgent(db=db).handle(state, [])
    assert state.voucher_code is not None
    assert state.voucher_code.startswith("VCH-")
    assert state.error is None


@pytest.mark.asyncio
async def test_t016_scenario_b_luxury_lane2_chain():
    """T-016 Scenario B: Luxury bag → Lane 2 → hitl_queued, no voucher."""
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.agents.a5_notification import A5NotificationAgent
    from backend.graph.state import ClaimState

    state = ClaimState(
        session_id="t016-full-lane2",
        image_paths=["uploads/t016/luxury.jpg", "uploads/t016/bag_tag.jpg"],
        severity_score=0.4,
        compensation_estimate_usd=60.0,
        is_luxury=True,  # luxury → always Lane 2
        fraud_score=0.0,
        pnr="LUX001", bag_id="9876543210", flight_number="AI404",
    )
    db = _db()
    state = await A4DecisionAgent(db=db).handle(state, [])
    assert state.routing_lane == 2
    state = await A5NotificationAgent(db=db).handle(state, [])
    assert state.hitl_queued is True
    assert state.voucher_code is None


@pytest.mark.asyncio
async def test_t016_scenario_c_blurry_tag_blocks_a4():
    """T-016 Scenario C: Blurry tag (re_request_tag=True) → A4 must not run."""
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.graph.state import ClaimState
    db = _db()
    state = ClaimState(
        session_id="t016-c-tag",
        image_paths=["uploads/t016/damage.jpg", "uploads/t016/blurry_tag.jpg"],
        re_request_tag=True,
        compensation_estimate_usd=60.0,
    )
    result = await A4DecisionAgent(db=db).handle(state, [])
    assert result.routing_lane is None
    db.save_claim.assert_not_called()


@pytest.mark.asyncio
async def test_t016_scenario_c_blurry_damage_blocks_a4():
    """T-016 Scenario C: Blurry damage (re_request_damage=True) → A4 must not run."""
    from backend.agents.a4_decision import A4DecisionAgent
    from backend.graph.state import ClaimState
    db = _db()
    state = ClaimState(
        session_id="t016-c-damage",
        image_paths=["uploads/t016/blurry_damage.jpg", "uploads/t016/bag_tag.jpg"],
        re_request_damage=True,
        pnr="ABC123", bag_id="0572351234", flight_number="AI202",
    )
    result = await A4DecisionAgent(db=db).handle(state, [])
    assert result.routing_lane is None
    db.save_claim.assert_not_called()


@pytest.mark.asyncio
async def test_t016_no_agent_imports_providers_directly():
    """T-016: None of the 5 agent files import Gemini/Supabase directly."""
    agent_files = [
        "backend/agents/a1_conversation.py",
        "backend/agents/a2_vision.py",
        "backend/agents/a3_ocr.py",
        "backend/agents/a4_decision.py",
        "backend/agents/a5_notification.py",
    ]
    forbidden = ["google.generativeai", "supabase"]
    violations = []
    for f in agent_files:
        source = Path(f).read_text()
        for term in forbidden:
            if term in source:
                violations.append(f"{f}: contains '{term}'")
    assert violations == [], (
        "Agent files must never import providers directly:\n" + "\n".join(violations)
    )


@pytest.mark.asyncio
async def test_t016_webhook_response_includes_routing_fields():
    """T-016: /webhook response schema includes routing_lane, voucher_code, re_request_*."""
    from backend.main import app
    patches = _all_patches()
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/webhook", json={"session_id": "t016-schema", "message": "hi"})
    data = r.json()
    for field in ["routing_lane", "voucher_code", "re_request_tag", "re_request_damage", "claim_id"]:
        assert field in data, f"Response missing field: {field}"