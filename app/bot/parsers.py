"""Парсеры ввода для бота: услуги (запятая, валюта, несколько строк), слоты расписания."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, time
from typing import Sequence, Tuple


def parse_price(price_str: str) -> float | None:
    """Извлекает число из строки цены, например '200 MYR' -> 200, '1 500' -> 1500."""
    s = price_str.strip()
    # Убираем пробелы между цифрами и оставляем одну точку/запятую как десятичный разделитель
    s = re.sub(r"\s+", "", s)
    match = re.search(r"[\d.,]+", s)
    if not match:
        return None
    num = match.group(0).replace(",", ".")
    try:
        return float(num)
    except ValueError:
        return None


def parse_services_text(text: str) -> list[Tuple[str, float, int]]:
    """
    Парсит блок текста с услугами. Разделитель — запятая, несколько услуг — перенос строки.
    Строка: название, цена (можно с валютой), длительность_мин.
    Возвращает список (name, price, duration_minutes) или пустой при ошибке.
    """
    def _parse_line(line: str) -> tuple[str, float, int] | None:
        """
        Accepts common real-world formats:
        - "Маникюр, 200 MYR, 60"
        - "Маникюр - 200 MYR - 60"
        - "Маникюр — 2000 — 60"
        - "Маникюр 2000 60"
        - "Маникюр 2000р 60мин"
        """
        raw = line.strip()
        if not raw:
            return None

        # Normalize separators to comma when it looks like a 3-field input.
        normalized = re.sub(r"\s*[—–-]\s*", ",", raw)
        normalized = re.sub(r"\s*;\s*", ",", normalized)
        parts = [p.strip() for p in normalized.split(",") if p.strip()]

        name: str | None = None
        price: float | None = None
        duration: int | None = None

        if len(parts) >= 3:
            name = parts[0]
            price = parse_price(parts[1])
            dur_match = re.search(r"\d+", parts[2])
            if dur_match:
                duration = int(dur_match.group(0))
        else:
            # Space-separated fallback: treat last int as duration, previous number-ish as price
            tokens = raw.split()
            if len(tokens) < 3:
                return None

            # duration: last integer found scanning from end
            dur_idx = None
            for i in range(len(tokens) - 1, -1, -1):
                m = re.fullmatch(r"\d{1,4}", re.sub(r"\D", "", tokens[i]))
                if m:
                    dur_idx = i
                    duration = int(re.sub(r"\D", "", tokens[i]))
                    break
            if dur_idx is None or duration is None:
                return None

            # price: scan left from duration for first token containing a number
            price_idx = None
            for j in range(dur_idx - 1, -1, -1):
                if re.search(r"\d", tokens[j]):
                    price_idx = j
                    price = parse_price(tokens[j])
                    break
            if price_idx is None or price is None:
                return None

            name = " ".join(tokens[:price_idx]).strip()

        if not name:
            return None
        if price is None or price <= 0:
            return None
        if duration is None or duration <= 0:
            return None

        return name, price, duration

    result: list[Tuple[str, float, int]] = []
    for line in text.strip().splitlines():
        parsed = _parse_line(line)
        if parsed is not None:
            result.append(parsed)
    return result


def parse_schedule_lines(
    text: str,
    *,
    default_year: int | None = None,
    today: date | None = None,
    skip_past: bool = True,
) -> list[Tuple[date, time]]:
    """
    Парсит расписание в формате:
    9/02 в 10:00
    20/02 в 10:00, 12:00, 16:00
    Также понимает вариант без «в»:
    20/02 10:00, 12:00, 16:00

    Возвращает список (slot_date, slot_time). Год: default_year или текущий.
    """
    today_val = today or date.today()
    year = default_year or today_val.year
    result = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if " в " in line:
            date_part, rest = line.split(" в ", 1)
        else:
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            date_part, rest = parts[0], parts[1]
        date_part = date_part.strip()
        times_part = rest.strip()
        try:
            d, m = map(int, date_part.split("/"))
        except ValueError:
            continue
        try:
            slot_date = date(year, m, d)
        except ValueError:
            continue
        if skip_past and slot_date < today_val:
            continue
        for t in times_part.split(","):
            t = t.strip()
            if not t:
                continue
            try:
                h, minu = map(int, t.split(":"))
                slot_time = time(h, minu)
            except ValueError:
                continue
            result.append((slot_date, slot_time))
    return result


def format_schedule_slots(slots: Sequence[Tuple[date, time]]) -> str:
    """Форматирует слоты (date, time) в вид: DD/MM в HH:MM, HH:MM, ... по датам."""
    by_date: dict[date, list[time]] = defaultdict(list)
    for slot_date, slot_time in slots:
        by_date[slot_date].append(slot_time)
    for d in by_date:
        by_date[d].sort()
    lines = []
    for d in sorted(by_date.keys()):
        times_str = ", ".join(t.strftime("%H:%M") for t in by_date[d])
        lines.append(f"{d.day}/{d.month:02d} в {times_str}")
    return "\n".join(lines) if lines else ""
