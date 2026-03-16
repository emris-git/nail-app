from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from openai import OpenAI

from app.config import get_settings


class ImageToTextAdapter(ABC):
    @abstractmethod
    async def extract_text(self, file_id: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class NoOpImageToTextAdapter(ImageToTextAdapter):
    async def extract_text(self, file_id: str) -> str:
        # For MVP we do not perform OCR; caller should ask user for text.
        return ""


class OpenAIImageToTextAdapter(ImageToTextAdapter):
    def __init__(self, api_key: Optional[str], api_base: Optional[str], model: Optional[str]):
        if not api_key:
            raise ValueError("LLM_API_KEY is required for OpenAIImageToTextAdapter")
        self._client = OpenAI(api_key=api_key, base_url=api_base or None)
        self._model = model or "gpt-4.1-mini"

    async def extract_text(self, file_id: str) -> str:
        """
        Здесь предполагается, что вызывающий код предварительно получает file_url
        или бинарные данные изображения и передаёт их как часть сообщения.
        Для простоты мы не реализуем полный Telegram file download, а только
        оставляем адаптер для использования с уже доступными байтами/URL.
        """
        # Базовый скелет на будущее — фактическая интеграция с Telegram file API
        # и вызовом vision-модели OpenAI будет добавлена, когда появится конкретный UX.
        return ""

