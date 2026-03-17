from __future__ import annotations

from app.bot.parsers import parse_services_text


def test_parse_services_text_commas():
    assert parse_services_text("Маникюр, 200 MYR, 60") == [("Маникюр", 200.0, 60)]


def test_parse_services_text_dashes():
    assert parse_services_text("Маникюр — 1500 — 60") == [("Маникюр", 1500.0, 60)]


def test_parse_services_text_spaces():
    assert parse_services_text("Маникюр 2000р 60мин") == [("Маникюр", 2000.0, 60)]

