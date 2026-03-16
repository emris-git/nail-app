from __future__ import annotations

from app.config import get_settings

from .base import PriceListParser
from .mock import MockPriceListParser
from .openai_parser import OpenAIPriceListParser


def get_price_list_parser() -> PriceListParser:
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAIPriceListParser(
            api_key=settings.llm_api_key,
            api_base=settings.llm_api_base,
            model=settings.llm_model,
        )
    return MockPriceListParser()

