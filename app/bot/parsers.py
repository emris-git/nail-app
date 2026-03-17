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
    result = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        name, price_str, dur_str = parts[0], parts[1], parts[2]
        price = parse_price(price_str)
        if price is None or price <= 0:
            continue
        try:
            duration = int(dur_str.strip())
            if duration <= 0:
                continue
        except ValueError:
            continue
        result.append((name, price, duration))
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
