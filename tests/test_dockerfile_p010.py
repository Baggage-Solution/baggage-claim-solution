"""tests/test_dockerfile_p010.py — P-010 Dockerfile structural validation.

These are static analysis tests — they read the Dockerfile and .dockerignore
files and assert structural correctness without doing any Docker build
(which is not available on office laptops per project constraint).

Covers:
  - Base image is python:3.11-slim.
  - Default CMD starts uvicorn on port 8000.
  - No secret values are baked into the image (no hardcoded keys).
  - .dockerignore excludes the required directories.
  - deploy/taskdef-api.json and taskdef-worker.json exist and are valid JSON.
  - Worker task def has the command override set.

Authors: Devam + Aditya + Anoushka (unified branch — P-010)
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest

# Path resolution: tests live in tests/, Dockerfile at repo root
REPO_ROOT = pathlib.Path(__file__).parent.parent
DOCKERFILE_PATH = REPO_ROOT / "Dockerfile"
DOCKERIGNORE_PATH = REPO_ROOT / ".dockerignore"
TASKDEF_API_PATH = REPO_ROOT / "deploy" / "taskdef-api.json"
TASKDEF_WORKER_PATH = REPO_ROOT / "deploy" / "taskdef-worker.json"


# ──────────────────────────────────────────────────────────────
# Dockerfile
# ──────────────────────────────────────────────────────────────

def test_dockerfile_exists():
    """Dockerfile must exist at repo root."""
    assert DOCKERFILE_PATH.exists(), f"Dockerfile not found at {DOCKERFILE_PATH}"


def test_dockerfile_base_image_is_python311_slim():
    """Base image must be python:3.11-slim for size and reproducibility."""
    content = DOCKERFILE_PATH.read_text()
    assert "FROM python:3.11-slim" in content, "Expected 'FROM python:3.11-slim'"


def test_dockerfile_exposes_port_8000():
    """Container must expose port 8000 (matches ALB target group config)."""
    content = DOCKERFILE_PATH.read_text()
    assert "EXPOSE 8000" in content


def test_dockerfile_default_cmd_is_uvicorn():
    """Default CMD must start uvicorn on 0.0.0.0:8000."""
    content = DOCKERFILE_PATH.read_text()
    assert "uvicorn" in content
    assert "0.0.0.0" in content
    assert "8000" in content


def test_dockerfile_has_healthcheck():
    """HEALTHCHECK instruction must be present for ECS task health tracking."""
    content = DOCKERFILE_PATH.read_text()
    assert "HEALTHCHECK" in content
    assert "/health" in content


def test_dockerfile_has_non_root_user():
    """App must run as non-root (principle of least privilege)."""
    content = DOCKERFILE_PATH.read_text()
    # Either useradd or USER instruction (non-root) must appear
    assert "useradd" in content or (
        "USER" in content and "root" not in content.split("USER")[1].split("\n")[0]
    )


def test_dockerfile_copies_requirements_before_source():
    """requirements.txt copy must precede source copy for layer caching."""
    content = DOCKERFILE_PATH.read_text()
    req_idx = content.find("requirements.txt")
    backend_idx = content.find("COPY backend/")
    assert req_idx < backend_idx, (
        "requirements.txt must be COPYed before backend/ for Docker layer caching"
    )


def test_dockerfile_no_hardcoded_secrets():
    """No API keys, access keys, or secret values must be baked into the image."""
    content = DOCKERFILE_PATH.read_text().lower()
    forbidden_patterns = [
        "api_key=",
        "secret_key=",
        "access_key=",
        "password=",
        "supabase_service_role_key=",
        "gemini_api_key=",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in content, (
            f"Possible secret hardcoded in Dockerfile: {pattern}"
        )


# ──────────────────────────────────────────────────────────────
# .dockerignore
# ──────────────────────────────────────────────────────────────

def test_dockerignore_exists():
    """.dockerignore must exist at repo root."""
    assert DOCKERIGNORE_PATH.exists()


def test_dockerignore_excludes_tests():
    """tests/ must be excluded — test code has no place in the prod image."""
    content = DOCKERIGNORE_PATH.read_text()
    assert "tests/" in content or "tests" in content


def test_dockerignore_excludes_frontend():
    """frontend/ must be excluded — it is built separately by Vite."""
    content = DOCKERIGNORE_PATH.read_text()
    assert "frontend/" in content or "frontend" in content


def test_dockerignore_excludes_env_files():
    """.env files must be excluded — secrets must not ship in the image."""
    content = DOCKERIGNORE_PATH.read_text()
    assert ".env" in content


def test_dockerignore_excludes_branch_docs():
    """BRANCH_DOCS/ is internal project management — not needed at runtime."""
    content = DOCKERIGNORE_PATH.read_text()
    assert "BRANCH_DOCS" in content


def test_dockerignore_excludes_git():
    """.git directory must not be in the image."""
    content = DOCKERIGNORE_PATH.read_text()
    assert ".git" in content


# ──────────────────────────────────────────────────────────────
# deploy/taskdef-api.json
# ──────────────────────────────────────────────────────────────

def test_taskdef_api_exists():
    """deploy/taskdef-api.json must exist as the ECS API task definition."""
    assert TASKDEF_API_PATH.exists()


def test_taskdef_api_is_valid_json():
    """taskdef-api.json must be valid JSON."""
    content = TASKDEF_API_PATH.read_text()
    parsed = json.loads(content)
    assert isinstance(parsed, dict)


def test_taskdef_api_has_image_uri_placeholder():
    """<IMAGE_URI> placeholder must be present — filled by GitHub Actions."""
    content = TASKDEF_API_PATH.read_text()
    assert "<IMAGE_URI>" in content


def test_taskdef_api_has_no_command_override():
    """API task def must use the default CMD (uvicorn), not a command override."""
    parsed = json.loads(TASKDEF_API_PATH.read_text())
    container = parsed["containerDefinitions"][0]
    # command field should be empty list or absent
    cmd = container.get("command", [])
    assert cmd == [], f"API task def must not override command; got: {cmd}"


def test_taskdef_api_enable_simulator_false():
    """ENABLE_SIMULATOR must be false in production task definition."""
    parsed = json.loads(TASKDEF_API_PATH.read_text())
    env = {
        e["name"]: e["value"]
        for e in parsed["containerDefinitions"][0].get("environment", [])
    }
    assert env.get("ENABLE_SIMULATOR") == "false"


# ──────────────────────────────────────────────────────────────
# deploy/taskdef-worker.json
# ──────────────────────────────────────────────────────────────

def test_taskdef_worker_exists():
    """deploy/taskdef-worker.json must exist as the ECS worker task definition."""
    assert TASKDEF_WORKER_PATH.exists()


def test_taskdef_worker_is_valid_json():
    """taskdef-worker.json must be valid JSON."""
    content = TASKDEF_WORKER_PATH.read_text()
    parsed = json.loads(content)
    assert isinstance(parsed, dict)


def test_taskdef_worker_has_command_override():
    """Worker task def MUST override command to ['python', '-m', 'backend.worker']."""
    parsed = json.loads(TASKDEF_WORKER_PATH.read_text())
    container = parsed["containerDefinitions"][0]
    cmd = container.get("command", [])
    assert cmd == ["python", "-m", "backend.worker"], (
        f"Worker task def command override missing or wrong; got: {cmd}"
    )


def test_taskdef_worker_has_image_uri_placeholder():
    """Worker must use the same image as the API — same <IMAGE_URI> placeholder."""
    content = TASKDEF_WORKER_PATH.read_text()
    assert "<IMAGE_URI>" in content


def test_taskdef_worker_same_env_vars_as_api():
    """Worker and API must share the same provider env vars (AWS, Bedrock, etc)."""
    api = json.loads(TASKDEF_API_PATH.read_text())
    worker = json.loads(TASKDEF_WORKER_PATH.read_text())

    api_env = {e["name"] for e in api["containerDefinitions"][0].get("environment", [])}
    worker_env = {e["name"] for e in worker["containerDefinitions"][0].get("environment", [])}

    required_in_both = {
        "LLM_PROVIDER", "VISION_PROVIDER", "OCR_PROVIDER",
        "STORAGE_PROVIDER", "QUEUE_PROVIDER", "SECRETS_PROVIDER",
        "AWS_REGION", "BEDROCK_LLM_MODEL",
    }
    for var in required_in_both:
        assert var in api_env, f"{var} missing from API task def"
        assert var in worker_env, f"{var} missing from worker task def"
