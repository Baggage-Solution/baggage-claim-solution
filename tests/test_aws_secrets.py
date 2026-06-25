from __future__ import annotations

import json

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from backend.secrets_provider.aws_secrets import AWSSecretsManagerProvider

TEST_SECRET_NAME = "baggage-claim/test"
TEST_REGION = "us-east-1"


def _create_test_secret(secret_data: dict, secret_name: str = TEST_SECRET_NAME) -> None:
    """Create a Secrets Manager secret under a moto mock for test setup."""
    client = boto3.client("secretsmanager", region_name=TEST_REGION)
    client.create_secret(Name=secret_name, SecretString=json.dumps(secret_data))


# ── Initialisation / fetch-and-cache tests ──────────────────────────────────────


@mock_aws
def test_init_fetches_and_caches_secret():
    """On init, the provider fetches the secret once and caches its parsed
    JSON contents in memory."""
    _create_test_secret(
        {"SUPABASE_URL": "https://test.supabase.co", "SUPABASE_ANON_KEY": "anon-123"}
    )

    provider = AWSSecretsManagerProvider(
        secret_name=TEST_SECRET_NAME, region=TEST_REGION
    )

    assert provider.get("SUPABASE_URL") == "https://test.supabase.co"
    assert provider.get("SUPABASE_ANON_KEY") == "anon-123"


@mock_aws
def test_init_raises_clienterror_for_nonexistent_secret():
    """A secret that doesn't exist raises ClientError at init time — the
    app should fail fast at startup rather than discover the problem on
    the first real secret lookup mid-request."""
    with pytest.raises(ClientError):
        AWSSecretsManagerProvider(secret_name="does-not-exist", region=TEST_REGION)


@mock_aws
def test_init_raises_valueerror_for_invalid_json_secret():
    """A secret whose SecretString is not valid JSON raises ValueError
    rather than silently caching garbage."""
    client = boto3.client("secretsmanager", region_name=TEST_REGION)
    client.create_secret(Name=TEST_SECRET_NAME, SecretString="not valid json {{{")

    with pytest.raises(ValueError):
        AWSSecretsManagerProvider(secret_name=TEST_SECRET_NAME, region=TEST_REGION)


@mock_aws
def test_get_does_not_make_additional_aws_calls():
    """Calling get() multiple times after init only ever reads from the
    in-memory cache — no repeated GetSecretValue calls. Verified by
    deleting the secret AFTER init and confirming get() still works,
    which is only possible if get() never re-fetches from AWS."""
    _create_test_secret({"SUPABASE_URL": "https://cached.supabase.co"})

    provider = AWSSecretsManagerProvider(
        secret_name=TEST_SECRET_NAME, region=TEST_REGION
    )

    client = boto3.client("secretsmanager", region_name=TEST_REGION)
    client.delete_secret(SecretId=TEST_SECRET_NAME, ForceDeleteWithoutRecovery=True)

    # If get() tried to re-fetch, this would raise ResourceNotFoundException —
    # it doesn't, because the value already lives in self._cache.
    assert provider.get("SUPABASE_URL") == "https://cached.supabase.co"


# ── get() lookup tests ──────────────────────────────────────────────────────────


@mock_aws
def test_get_raises_keyerror_for_missing_key():
    """A key not present in the secret JSON raises KeyError, matching
    EnvSecretsProvider's contract for a missing variable."""
    _create_test_secret({"SUPABASE_URL": "https://test.supabase.co"})

    provider = AWSSecretsManagerProvider(
        secret_name=TEST_SECRET_NAME, region=TEST_REGION
    )

    with pytest.raises(KeyError):
        provider.get("META_ACCESS_TOKEN")  # not in this secret


@mock_aws
def test_get_returns_string_even_for_non_string_json_values():
    """A secret value that happens to be a JSON number/bool is coerced to
    str() — SecretsProvider.get()'s contract is always str."""
    _create_test_secret({"SOME_NUMERIC_FLAG": 12345})

    provider = AWSSecretsManagerProvider(
        secret_name=TEST_SECRET_NAME, region=TEST_REGION
    )

    result = provider.get("SOME_NUMERIC_FLAG")
    assert result == "12345"
    assert isinstance(result, str)


@mock_aws
def test_get_handles_multiple_keys_in_one_secret():
    """A single secret JSON blob can hold several unrelated credentials —
    matches the task's 'Bedrock + Supabase + Meta creds all live in ONE
    secret JSON' design."""
    _create_test_secret(
        {
            "SUPABASE_URL": "https://multi.supabase.co",
            "SUPABASE_ANON_KEY": "anon-456",
            "SUPABASE_SERVICE_ROLE_KEY": "service-789",
        }
    )

    provider = AWSSecretsManagerProvider(
        secret_name=TEST_SECRET_NAME, region=TEST_REGION
    )

    assert provider.get("SUPABASE_URL") == "https://multi.supabase.co"
    assert provider.get("SUPABASE_ANON_KEY") == "anon-456"
    assert provider.get("SUPABASE_SERVICE_ROLE_KEY") == "service-789"


@mock_aws
def test_get_on_empty_secret_raises_keyerror_for_any_key():
    """An empty JSON object {} is valid JSON but yields KeyError for any
    lookup — distinct failure mode from the invalid-JSON case."""
    _create_test_secret({})

    provider = AWSSecretsManagerProvider(
        secret_name=TEST_SECRET_NAME, region=TEST_REGION
    )

    with pytest.raises(KeyError):
        provider.get("SUPABASE_URL")