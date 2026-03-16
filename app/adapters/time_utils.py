from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo


def make_timezone(name: str) -> timezone:
    return ZoneInfo(name)

