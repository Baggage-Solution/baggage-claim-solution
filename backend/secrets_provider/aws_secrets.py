from __future__ import annotations

import json
import logging

import boto3
from botocore.exceptions import ClientError

from backend.secrets_provider.base import SecretsProvider

logger = logging.getLogger(__name__)


class AWSSecretsManagerProvider(SecretsProvider):
    """
    AWS Secrets Manager secrets provider (Production — P-005).

    On init, fetches a single JSON-blob secret from Secrets Manager and
    caches it in memory for the lifetime of the process — exactly once,
    not on every get() call. This mirrors the "cache once at startup"
    requirement in the task notes and avoids a network round-trip on
    every secret lookup (which would otherwise happen on every request
    that touches a DB-backed agent).

    The secret itself is one JSON object holding every AWS-sourced
    credential the app needs — Supabase keys today, Meta WhatsApp
    credentials once P-021 lands — under a single secret name
    (baggage-claim/<env>), rather than one Secrets Manager secret per
    credential. This keeps the admin-provisioning surface small (one
    secret to create, one IAM policy to scope) and matches exactly what
    P-013's admin ticket asks for.

    Swap path: set SECRETS_PROVIDER=env to fall back to EnvSecretsProvider
    (POC/local dev), or implement a new SecretsProvider for another vault
    (e.g. HashiCorp Vault) — no other code changes required.
    """

    def __init__(self, secret_name: str, region: str) -> None:
        """
        Initialise the provider and eagerly fetch + cache the secret.

        Fetching happens here, in __init__, rather than lazily on first
        get() call — this is a deliberate "fail fast at startup" choice:
        if the secret is missing, malformed, or IAM permissions are wrong,
        the app should refuse to start rather than serve traffic and only
        discover the problem on the first real secret lookup.

        Args:
            secret_name: Name of the Secrets Manager secret (e.g.
                "baggage-claim/prod"). Read from Settings.secrets_manager_name
                — never hardcoded.
            region: AWS region the secret lives in (e.g. us-east-1).

        Raises:
            ClientError: If the secret cannot be fetched (missing, no
                permission, wrong region, etc.) — propagates immediately
                so startup fails loudly rather than masking the problem.
            ValueError: If the secret's value is not valid JSON.
        """
        self._secret_name = secret_name
        client = boto3.client("secretsmanager", region_name=region)

        try:
            response = client.get_secret_value(SecretId=secret_name)
        except ClientError:
            logger.exception(
                "aws_secrets_fetch_failed",
                extra={"secret_name": secret_name, "region": region},
            )
            raise

        raw_value = response.get("SecretString", "")
        try:
            self._cache: dict = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            logger.error(
                "aws_secrets_invalid_json",
                extra={"secret_name": secret_name},
            )
            raise ValueError(f"Secret '{secret_name}' is not valid JSON") from exc

        logger.info(
            "aws_secrets_loaded",
            extra={
                "secret_name": secret_name,
                "key_count": len(self._cache),
            },
        )

    def get(self, name: str) -> str:
        """Return a named secret's value from the in-memory cache.

        No network call happens here — the secret JSON was already
        fetched and parsed once in __init__.

        Args:
            name: The secret's key name within the JSON blob (e.g.
                SUPABASE_SERVICE_ROLE_KEY).

        Returns:
            str: The secret value.

        Raises:
            KeyError: If the named key is not present in the cached secret.
        """
        if name not in self._cache:
            logger.warning(
                "aws_secrets_key_missing",
                extra={"secret_name": self._secret_name, "key": name},
            )
            raise KeyError(f"Secret key '{name}' not found in '{self._secret_name}'")
        return str(self._cache[name])