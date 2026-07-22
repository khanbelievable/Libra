from decimal import Decimal

import pytest

from datalibra.domain.normalization import (
    decimal_string,
    normalize_country,
    normalize_date,
    normalize_identifier,
    parse_decimal,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [("Germany", "DE"), ("gbr", "GB"), (" Türkiye ", "TR"), ("NLD", "NL")],
)
def test_country_aliases_are_iso_alpha_2(source: str, expected: str) -> None:
    assert normalize_country(source) == expected


def test_dates_accept_explicit_regional_formats() -> None:
    assert normalize_date("2025-03-14") == "2025-03-14"
    assert normalize_date("14/03/2025") == "2025-03-14"
    assert normalize_date("14.03.2025") == "2025-03-14"


def test_invalid_dates_are_not_silently_coerced() -> None:
    with pytest.raises(ValueError, match="invalid date"):
        normalize_date("31/02/2025")


def test_decimal_and_identifier_standardization() -> None:
    assert parse_decimal(" 1234,50 ") == Decimal("1234.50")
    assert decimal_string(Decimal("1.005"), Decimal("0.01")) == "1.01"
    assert normalize_identifier(" cus-de-001 ") == "CUS-DE-001"
