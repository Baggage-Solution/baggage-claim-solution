from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from backend.graph.state import ClaimState


class BaseAgent(ABC):
    """
    Abstract base for all 5 claim-processing agents.
    Direct copy from Proj A enterprise-chatbot-framework base_agent.py.

    All agents extend this and implement handle().
    No agent ever imports a provider directly — providers are injected via __init__.
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description

    @abstractmethod
    async def handle(
        self,
        state: ClaimState,
        tasks: List[str],
    ) -> ClaimState:
        """
        Process the current state and return the updated state.
        Never raise — catch exceptions internally and call state.set_error().
        """
        raise NotImplementedError
