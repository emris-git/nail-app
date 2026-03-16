from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator


class ParsedService(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    price: float = Field(..., gt=0, lt=1_000_000)
    duration_minutes: Optional[int] = Field(default=None, gt=0, lt=24 * 60)


class PriceListParseResult(BaseModel):
    services: List[ParsedService] = Field(default_factory=list, max_length=200)
    raw_text: str

    @field_validator("services")
    @classmethod
    def validate_non_empty(cls, v: List[ParsedService]) -> List[ParsedService]:
        if not v:
            raise ValueError("Price list must contain at least one service.")
        return v


def validate_price_list_result(data: dict) -> PriceListParseResult:
    try:
        return PriceListParseResult.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid price list structure: {exc}") from exc

