from __future__ import annotations

import logging
import os

from backend.secrets_provider.base import SecretsProvider

logger = logging.getLogger(__name__)


class EnvSecretsProvider(SecretsProvider):
    """
    Reads secrets straight from process environment variables / .env (POC — zero cost).
    Future swap: set SECRETS_PROVIDER=aws_sm → aws_secrets.py (P-005),
    which reads everything from one Secrets Manager JSON blob instead.
    """

    def get(self, name: str) -> str:
        """Return an environment variable's value.

        Args:
            name: The environment variable name.

        Returns:
            str: The value.

        Raises:
            KeyError: If the variable is not set.
        """
        value = os.environ.get(name)
        if value is None:
            logger.warning("env_secrets_missing", extra={"name": name})
            raise KeyError(f"Secret '{name}' not found in environment")
        return value
