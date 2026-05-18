from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DamageResult:
    damage_types: List[str] = field(default_factory=list)
    severity_score: float = 0.0       # 0.0 (cosmetic) to 1.0 (destroyed)
    confidence: float = 0.0
    raw_description: str = ""


@dataclass
class BrandResult:
    brand: Optional[str] = None
    is_luxury: bool = False
    confidence: float = 0.0


class VisionProvider(ABC):
    """
    Abstract interface for damage image analysis.
    Following Proj A provider ABC pattern — no agent ever imports a concrete class.
    Swap by changing VISION_PROVIDER env var and implementing a new subclass.
    """

    @abstractmethod
    async def analyze_damage(self, image_path: str) -> DamageResult:
        """
        Analyse a damage photo.
        Returns damage type list + severity score.
        """
        raise NotImplementedError

    @abstractmethod
    async def classify_brand(self, image_path: str) -> BrandResult:
        """
        Detect luggage brand and determine if it is a luxury item.
        """
        raise NotImplementedError
