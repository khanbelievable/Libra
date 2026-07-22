"""Canonical field normalization and exact financial arithmetic."""

from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

COUNTRY_ALIASES = {
    "DE": "DE",
    "DEU": "DE",
    "GERMANY": "DE",
    "NL": "NL",
    "NLD": "NL",
    "NETHERLANDS": "NL",
    "FR": "FR",
    "FRA": "FR",
    "FRANCE": "FR",
    "GB": "GB",
    "GBR": "GB",
    "UK": "GB",
    "UNITED KINGDOM": "GB",
    "TR": "TR",
    "TUR": "TR",
    "TÜRKIYE": "TR",
    "TURKIYE": "TR",
    "TURKEY": "TR",
}


def normalize_code(value: str) -> str:
    return value.strip().upper()


def normalize_country(value: str) -> str:
    normalized = normalize_code(value)
    return COUNTRY_ALIASES.get(normalized, normalized)


def normalize_identifier(value: str) -> str:
    return normalize_code(value).replace(" ", "-")


def normalize_date(value: str) -> str:
    """Accept the source contract's unambiguous ISO-8601 calendar date."""

    raw = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError(f"Unsupported or invalid date: {value!r}")
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as error:
        raise ValueError(f"Unsupported or invalid date: {value!r}") from error


def parse_decimal(value: str) -> Decimal:
    raw = value.strip()
    if "," in raw or " " in raw:
        raise ValueError(f"Ambiguous decimal: {value!r}")
    try:
        parsed = Decimal(raw)
    except InvalidOperation as error:
        raise ValueError(f"Invalid decimal: {value!r}") from error
    if not parsed.is_finite():
        raise ValueError(f"Non-finite decimal: {value!r}")
    return parsed


def decimal_string(value: Decimal, scale: Decimal) -> str:
    if not value.is_finite():
        raise ValueError(f"Cannot persist non-finite decimal: {value!r}")
    return format(value.quantize(scale, rounding=ROUND_HALF_UP), "f")
