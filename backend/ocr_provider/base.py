from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TagData:
    """Structured result returned by OCR extraction from a bag tag image.

    Fields default to None when the corresponding value could not be read.
    confidence reflects the OCR model's overall certainty for this image.
    """

    flight_number: Optional[str] = None
    pnr: Optional[str] = None
    bag_id: Optional[str] = None
    confidence: float = 0.0


class OCRProvider(ABC):
    """
    Abstract interface for bag tag OCR extraction.
    Swap by changing OCR_PROVIDER env var.
    Future: implement PaddleOCRProvider in paddleocr.py (runs fully offline).
    """

    @abstractmethod
    async def extract_bag_tag(self, image_path: str) -> TagData:
        """
        Extract flight_number, pnr, bag_id from a bag tag photo.
        Returns TagData with confidence score.
        """
        raise NotImplementedError
