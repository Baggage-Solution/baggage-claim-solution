from __future__ import annotations

import json
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from backend.config import get_settings

TEST_SECRET_NAME = "baggage-claim/test-config"
TEST_REGION = "us-east-1"


@pytest.fixture(autouse=True)
def _clean_settings_cache():
    """Clear the get_settings() lru_cache before and after every test in
    this file so tests never see another test's cached Settings instance."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure SECRETS_PROVIDER/SECRETS_MANAGER_NAME/AWS_REGION never leak
    between tests via the real process environment."""
    monkeypatch.delenv("SECRETS_PROVIDER", raising=False)
    monkeypatch.delenv("SECRETS_MANAGER_NAME", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)


def _create_test_secret(secret_data: dict) -> None:
    client = boto3.client("secretsmanager", region_name=TEST_REGION)
    client.create_secret(Name=TEST_SECRET_NAME, SecretString=json.dumps(secret_data))


# ── Default (SECRETS_PROVIDER=env) — must be completely unaffected ─────────────


def test_get_settings_default_provider_is_env(monkeypatch):
    """With no SECRETS_PROVIDER set, Settings behaves exactly as it did
    before P-005 — no Secrets Manager call is attempted at all.

    Asserts behaviour (boto3.client is never called), not a specific
    field VALUE — supabase_url's actual value depends on whatever the
    developer's local .env happens to contain, which is not what this
    test is meant to verify.
    """
    with patch("boto3.client") as mock_boto_client:
        settings = get_settings()

    assert settings.secrets_provider == "env"
    mock_boto_client.assert_not_called()


def test_get_settings_env_provider_reads_from_environment(monkeypatch):
    """With SECRETS_PROVIDER=env explicitly set, regular env vars are read
    as before — Secrets Manager is never touched."""
    monkeypatch.setenv("SECRETS_PROVIDER", "env")
    monkeypatch.setenv("SUPABASE_URL", "https://from-env.supabase.co")

    settings = get_settings()

    assert settings.supabase_url == "https://from-env.supabase.co"


# ── SECRETS_PROVIDER=aws_sm — the new P-005 path ────────────────────────────────


@mock_aws
def test_get_settings_aws_sm_overrides_matching_fields(monkeypatch):
    """When SECRETS_PROVIDER=aws_sm, fields present in the secret JSON are
    populated from Secrets Manager rather than .env — the core P-005
    acceptance criterion."""
    _create_test_secret(
        {
            "SUPABASE_URL": "https://from-secrets-manager.supabase.co",
            "SUPABASE_ANON_KEY": "vault-anon-key",
            "SUPABASE_SERVICE_ROLE_KEY": "vault-service-key",
        }
    )
    monkeypatch.setenv("SECRETS_PROVIDER", "aws_sm")
    monkeypatch.setenv("SECRETS_MANAGER_NAME", TEST_SECRET_NAME)
    monkeypatch.setenv("AWS_REGION", TEST_REGION)

    settings = get_settings()

    assert settings.supabase_url == "https://from-secrets-manager.supabase.co"
    assert settings.supabase_anon_key == "vault-anon-key"
    assert settings.supabase_service_role_key == "vault-service-key"


@mock_aws
def test_get_settings_aws_sm_ignores_dotenv_value_when_secret_has_it(monkeypatch):
    """A SUPABASE_URL set via env var is OVERRIDDEN by the Secrets Manager
    value when SECRETS_PROVIDER=aws_sm — the secret wins, proving this
    isn't just a fallback-if-env-missing behaviour."""
    _create_test_secret({"SUPABASE_URL": "https://vault-wins.supabase.co"})
    monkeypatch.setenv("SECRETS_PROVIDER", "aws_sm")
    monkeypatch.setenv("SECRETS_MANAGER_NAME", TEST_SECRET_NAME)
    monkeypatch.setenv("AWS_REGION", TEST_REGION)
    # Deliberately ALSO set a conflicting .env-style value
    monkeypatch.setenv("SUPABASE_URL", "https://dotenv-loses.supabase.co")

    settings = get_settings()

    assert settings.supabase_url == "https://vault-wins.supabase.co"


@mock_aws
def test_get_settings_aws_sm_partial_secret_keeps_dotenv_for_missing_keys(
    monkeypatch,
):
    """If the secret JSON only has SOME of the mapped keys, fields absent
    from the secret keep their .env/default value rather than being wiped
    to None — a partially-populated secret degrades gracefully."""
    _create_test_secret({"SUPABASE_URL": "https://only-this-key.supabase.co"})
    # SUPABASE_ANON_KEY intentionally NOT in the secret
    monkeypatch.setenv("SECRETS_PROVIDER", "aws_sm")
    monkeypatch.setenv("SECRETS_MANAGER_NAME", TEST_SECRET_NAME)
    monkeypatch.setenv("AWS_REGION", TEST_REGION)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "https://this-stays-from-dotenv")

    settings = get_settings()

    assert settings.supabase_url == "https://only-this-key.supabase.co"
    assert settings.supabase_anon_key == "https://this-stays-from-dotenv"


@mock_aws
def test_get_settings_aws_sm_does_not_override_non_secret_fields(monkeypatch):
    """Provider switches, model IDs, and thresholds are NEVER overridden
    by Secrets Manager, even if a secret happened to contain a key with
    a matching name — only fields in _SECRET_FIELD_MAP are eligible."""
    _create_test_secret(
        {
            "SUPABASE_URL": "https://test.supabase.co",
            "LLM_PROVIDER": "this-should-never-apply",  # not in the map
        }
    )
    monkeypatch.setenv("SECRETS_PROVIDER", "aws_sm")
    monkeypatch.setenv("SECRETS_MANAGER_NAME", TEST_SECRET_NAME)
    monkeypatch.setenv("AWS_REGION", TEST_REGION)
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")

    settings = get_settings()

    assert settings.llm_provider == "bedrock"  # unaffected by the secret


@mock_aws
def test_get_settings_aws_sm_uses_secrets_manager_name_setting(monkeypatch):
    """The secret name to fetch is itself read from SECRETS_MANAGER_NAME
    (an env var), not hardcoded — confirms the chicken-and-egg problem
    (needing config to know which secret to load) is solved correctly."""
    custom_name = "baggage-claim/custom-name-test"
    client = boto3.client("secretsmanager", region_name=TEST_REGION)
    client.create_secret(
        Name=custom_name,
        SecretString=json.dumps({"SUPABASE_URL": "https://custom-secret.supabase.co"}),
    )
    monkeypatch.setenv("SECRETS_PROVIDER", "aws_sm")
    monkeypatch.setenv("SECRETS_MANAGER_NAME", custom_name)
    monkeypatch.setenv("AWS_REGION", TEST_REGION)

    settings = get_settings()

    assert settings.supabase_url == "https://custom-secret.supabase.co"


def test_get_settings_caches_result_via_lru_cache(monkeypatch):
    """Two consecutive calls to get_settings() (without clearing the cache
    in between) return the exact same object — confirms @lru_cache is
    still in effect after the P-005 changes."""
    first = get_settings()
    second = get_settings()

    assert first is second