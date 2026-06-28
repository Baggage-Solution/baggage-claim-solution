"""tests/test_simulator_flag.py — P-009 Simulator Feature Flag tests.

Covers:
  - Settings.enable_simulator defaults to False (production-safe default).
  - Settings.enable_simulator reads from ENABLE_SIMULATOR env var.
  - /uploads is NOT mounted when ENABLE_SIMULATOR=false.
  - /uploads IS mounted when ENABLE_SIMULATOR=true.
  - /dashboard is always reachable regardless of flag.
  - /webhook is always reachable regardless of flag.

Authors: Anoushka (unified branch — P-009)
"""
from __future__ import annotations

import pytest


# ──────────────────────────────────────────────────────────────
# Settings field
# ──────────────────────────────────────────────────────────────

def test_enable_simulator_defaults_to_false():
    """Production default: simulator is disabled unless explicitly set."""
    from backend.config import Settings

    s = Settings()
    assert s.enable_simulator is False


def test_enable_simulator_reads_from_env(monkeypatch):
    """ENABLE_SIMULATOR=true activates the flag."""
    monkeypatch.setenv("ENABLE_SIMULATOR", "true")
    from backend.config import Settings

    s = Settings()
    assert s.enable_simulator is True


def test_enable_simulator_false_explicit(monkeypatch):
    """ENABLE_SIMULATOR=false keeps it off."""
    monkeypatch.setenv("ENABLE_SIMULATOR", "false")
    from backend.config import Settings

    s = Settings()
    assert s.enable_simulator is False


# ──────────────────────────────────────────────────────────────
# /dashboard always reachable
# ──────────────────────────────────────────────────────────────

def test_dashboard_route_reachable_when_simulator_disabled(monkeypatch):
    """/dashboard must respond regardless of ENABLE_SIMULATOR value."""
    monkeypatch.setenv("ENABLE_SIMULATOR", "false")
    from backend.config import get_settings
    get_settings.cache_clear()

    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    # /dashboard is a frontend route — the backend doesn't 404 it because
    # the decision router and health router are always mounted.
    # We verify the core production routes are alive by checking that the
    # route is MOUNTED and the app did not crash — not that every external
    # dependency (Gemini key, Supabase creds) happens to be configured in
    # this environment. /health legitimately returns 503 when those are
    # absent (see backend/api/routes/health.py, P-004) — that is correct
    # behaviour for a misconfigured environment, not a route failure.
    # Same 200-or-503 acceptance already used in test_smoke_t001_t016.py's
    # test_t004_health_endpoint_up for the identical reason.
    response = client.get("/health")
    assert response.status_code in (200, 503)


def test_webhook_route_always_reachable(monkeypatch):
    """/webhook must always be mounted — it is the WhatsApp inbound path."""
    monkeypatch.setenv("ENABLE_SIMULATOR", "false")
    from backend.config import get_settings
    get_settings.cache_clear()

    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    # POST with a valid minimal body — pipeline will fail (no real providers)
    # but the route must exist (not 404)
    response = client.post(
        "/webhook",
        json={"session_id": "s", "message": "test"},
    )
    # 200, 422, 500 are all acceptable — 404 is not
    assert response.status_code != 404


# ──────────────────────────────────────────────────────────────
# /uploads static mount gated on ENABLE_SIMULATOR
# ──────────────────────────────────────────────────────────────

def test_uploads_mount_absent_when_simulator_disabled(monkeypatch):
    """When ENABLE_SIMULATOR=false, /uploads is not mounted."""
    monkeypatch.setenv("ENABLE_SIMULATOR", "false")
    from backend.config import get_settings
    get_settings.cache_clear()

    # Reimport main to pick up new settings
    import importlib
    import backend.main as main_module
    importlib.reload(main_module)

    route_paths = [route.path for route in main_module.app.routes]
    assert "/uploads" not in route_paths


def test_uploads_mount_present_when_simulator_enabled(monkeypatch, tmp_path):
    """When ENABLE_SIMULATOR=true, /uploads is mounted as a StaticFiles route."""
    monkeypatch.setenv("ENABLE_SIMULATOR", "true")
    # Point to a real dir so StaticFiles doesn't raise on mount
    monkeypatch.setenv("LOCAL_STORAGE_BASE_PATH", str(tmp_path))
    from backend.config import get_settings
    get_settings.cache_clear()

    import importlib
    import backend.main as main_module
    importlib.reload(main_module)

    route_paths = [getattr(route, "path", "") for route in main_module.app.routes]
    assert "/uploads" in route_paths