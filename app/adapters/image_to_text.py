from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol


class ImageToTextAdapter(ABC):
    @abstractmethod
    async def extract_text(self, file_id: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class NoOpImageToTextAdapter(ImageToTextAdapter):
    async def extract_text(self, file_id: str) -> str:
        # For MVP we do not perform OCR; caller should ask user for text.
        return ""

