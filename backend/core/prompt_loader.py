from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class PromptLoader:
    """
    Loads JSON prompt templates from backend/prompts/ and renders them.
    Direct copy from Proj A enterprise-chatbot-framework.
    """

    PROMPT_DIR = Path("backend/prompts")

    @classmethod
    @lru_cache(maxsize=None)
    def load(cls, name: str) -> Dict[str, Any]:
        """Load and cache a JSON prompt template from backend/prompts/.

        Args:
            name: Template filename without extension (e.g. "a1_conversation").

        Returns:
            Dict[str, Any]: Parsed JSON prompt structure.

        Raises:
            FileNotFoundError: If no matching .json file exists.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        path = cls.PROMPT_DIR / f"{name}.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(
                "prompt_not_found", extra={"prompt_name": name, "path": str(path)}
            )
            raise
        except json.JSONDecodeError:
            logger.error(
                "prompt_invalid_json", extra={"prompt_name": name, "path": str(path)}
            )
            raise

    @staticmethod
    def render(template: str, variables: Dict[str, Any]) -> str:
        """Replace {variable} placeholders in a prompt template string."""
        try:
            return template.format(**variables)
        except KeyError as e:
            logger.error("prompt_variable_missing", extra={"missing_variable": str(e)})
            raise
