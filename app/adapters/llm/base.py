from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.price_list import PriceListParseResult


class PriceListParser(ABC):
    @abstractmethod
    async def parse(self, text: str) -> PriceListParseResult:  # pragma: no cover - interface
        raise NotImplementedError

