from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DamageResult:
    damage_types: List[str] = field(default_factory=list)
    severity_score: float = 0.0  # 0.0 (cosmetic) to 1.0 (destroyed)
    confidence: float = 0.0
    raw_description: str = ""


@dataclass
class BrandResult:
    brand: Optional[str] = None
    is_luxury: bool = False
    confidence: float = 0.0


@dataclass
class SceneResult:
    """
    Combined result of a single vision pass over one image.

    This is what lets the system answer, in ONE Gemini call, the three
    questions the pipeline actually needs about any uploaded photo:

      1. Is this even a piece of luggage?      → is_bag / bag_confidence
      2. If so, is it damaged and how badly?    → damage_*
      3. What brand is it (luxury?)             → brand / is_luxury
      4. Is a readable bag tag visible in it?   → tag_visible / tag_confidence

    Question 1 fixes issue #1 (non-bag images being treated as bags).
    Question 4 fixes issues #2 and #4 (a damage photo that also shows a tag,
    or a single combined photo) — the OCR step can then be attempted on the
    same image instead of only on files named "tag_*".
    """

    # ── Object gate ────────────────────────────────────────────────────────────
    is_bag: bool = False
    bag_confidence: float = 0.0  # how sure we are it IS luggage
    object_description: str = ""  # what the model thinks it is (for logging/UX)

    # ── Damage ───────────────────────────────────────────────────────────────
    damage_types: List[str] = field(default_factory=list)
    severity_score: float = 0.0
    damage_confidence: float = 0.0

    # ── Brand ──────────────────────────────────────────────────────────────────
    brand: Optional[str] = None
    is_luxury: bool = False
    brand_confidence: float = 0.0

    # ── Tag presence ───────────────────────────────────────────────────────────
    # True when a baggage tag (the printed label with barcode/flight number) is
    # visible and legible enough in THIS image that OCR is worth attempting.
    tag_visible: bool = False
    tag_confidence: float = 0.0

    raw_description: str = ""

    def to_damage_result(self) -> DamageResult:
        return DamageResult(
            damage_types=list(self.damage_types),
            severity_score=self.severity_score,
            confidence=self.damage_confidence,
            raw_description=self.raw_description,
        )

    def to_brand_result(self) -> BrandResult:
        return BrandResult(
            brand=self.brand,
            is_luxury=self.is_luxury,
            confidence=self.brand_confidence,
        )


class VisionProvider(ABC):
    """
    Abstract interface for luggage image analysis.
    Following Proj A provider ABC pattern — no agent ever imports a concrete class.
    Swap by changing VISION_PROVIDER env var and implementing a new subclass.
    """

    @abstractmethod
    async def analyze_image(self, image_path: str) -> SceneResult:
        """
        Single-pass analysis of one image: object gate + damage + brand + tag
        presence, all in one call. This is the primary method agents should use.
        """
        raise NotImplementedError

    @abstractmethod
    async def analyze_damage(self, image_path: str) -> DamageResult:
        """Backwards-compatible damage-only analysis (kept for existing tests)."""
        raise NotImplementedError

    @abstractmethod
    async def classify_brand(self, image_path: str) -> BrandResult:
        """Backwards-compatible brand-only classification (kept for existing tests)."""
        raise NotImplementedError