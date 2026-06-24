from __future__ import annotations

from abc import ABC, abstractmethod


class SecretsProvider(ABC):
    """
    Abstract interface for reading application secrets.
    Swap by changing SECRETS_PROVIDER env var.
    Future: implement AWSSecretsManagerProvider (P-005), reading the
    baggage-claim/<env> secret once at startup and caching in memory.
    """

    @abstractmethod
    def get(self, name: str) -> str:
        """Return the value of a named secret.

        Args:
            name: The secret's key name (e.g. SUPABASE_SERVICE_ROLE_KEY).

        Returns:
            str: The secret value.
        """
        raise NotImplementedError
