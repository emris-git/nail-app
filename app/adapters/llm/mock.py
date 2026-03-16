from __future__ import annotations

from app.domain.price_list import ParsedService, PriceListParseResult

from .base import PriceListParser


class MockPriceListParser(PriceListParser):
    async def parse(self, text: str) -> PriceListParseResult:
        # Very naive implementation: each non-empty line "name - price"
        services: list[ParsedService] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if "-" in line:
                name_part, price_part = line.split("-", 1)
            else:
                name_part, price_part = line, "0"
            try:
                price = float(price_part.strip().split()[0])
            except ValueError:
                price = 0.0
            if price <= 0:
                continue
            services.append(
                ParsedService(name=name_part.strip(), price=price, duration_minutes=60)
            )
        return PriceListParseResult(services=services, raw_text=text)

