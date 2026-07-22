"""Canonical field normalization and exact financial arithmetic."""

from __future__ import annotations

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
    """Accept the explicit source formats and persist ISO-8601 dates."""

    raw = value.strip()
    for separator, order in (("-", "ymd"), ("/", "dmy"), (".", "dmy")):
        parts = raw.split(separator)
        if len(parts) != 3:
            continue
        try:
            if order == "ymd":
                parsed = date(int(parts[0]), int(parts[1]), int(parts[2]))
            else:
                parsed = date(int(parts[2]), int(parts[1]), int(parts[0]))
        except ValueError:
            continue
        return parsed.isoformat()
    raise ValueError(f"Unsupported or invalid date: {value!r}")


def parse_decimal(value: str) -> Decimal:
    raw = value.strip().replace(" ", "")
    if raw.count(",") == 1 and "." not in raw:
        raw = raw.replace(",", ".")
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
