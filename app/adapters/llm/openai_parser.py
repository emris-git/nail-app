from __future__ import annotations

import json
from typing import Any, Dict, Optional

from openai import OpenAI

from app.config import get_settings
from app.domain.price_list import PriceListParseResult, validate_price_list_result

from .base import PriceListParser


SYSTEM_PROMPT = """
Ты помощник для бьюти-мастера. На вход получаешь текстовый прайс-лист услуг (маникюр и т.п.).
Твоя задача — вернуть JSON строго в формате:
{
  "raw_text": "<исходный текст как есть>",
  "services": [
    {
      "name": "<название услуги>",
      "price": <число>,
      "duration_minutes": <число или null>
    }
  ]
}

Требования:
- name — не пустая строка;
- price — положительное число (в рублях);
- duration_minutes — в минутах, > 0 и разумная (обычно 15–240), либо null, если непонятно;
- services — не более 100 позиций;
- Никакого текста кроме JSON.
"""


class OpenAIPriceListParser(PriceListParser):
    def __init__(
        self,
        api_key: Optional[str],
        api_base: Optional[str],
        model: Optional[str],
    ) -> None:
        if not api_key:
            raise ValueError("LLM_API_KEY is required for OpenAIPriceListParser")
        self._client = OpenAI(api_key=api_key, base_url=api_base or None)
        self._model = model or "gpt-4.1-mini"

    async def parse(self, text: str) -> PriceListParseResult:
        settings = get_settings()
        raw_text = text

        completion = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            response_format={"type": "json_object"},
        )

        content = completion.choices[0].message.content or "{}"
        data: Dict[str, Any] = json.loads(content)
        if "raw_text" not in data:
            data["raw_text"] = raw_text
        return validate_price_list_result(data)

