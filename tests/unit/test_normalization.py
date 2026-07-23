from decimal import Decimal

import pytest

from datalibra.config import load_project_config
from datalibra.domain.normalization import (
    decimal_string,
    normalize_country,
    normalize_date,
    normalize_identifier,
    parse_decimal,
)
from datalibra.silver.pipeline import _standardize_dimension, _standardize_fact


@pytest.mark.parametrize(
    ("source", "expected"),
    [("Germany", "DE"), ("gbr", "GB"), (" Türkiye ", "TR"), ("NLD", "NL")],
)
def test_country_aliases_are_iso_alpha_2(source: str, expected: str) -> None:
    assert normalize_country(source) == expected


def test_dates_accept_iso_source_contract() -> None:
    assert normalize_date("2025-03-14") == "2025-03-14"


@pytest.mark.parametrize("value", ["2025-02-31", "01/02/2025", "14.03.2025"])
def test_invalid_or_ambiguous_dates_are_not_silently_coerced(value: str) -> None:
    with pytest.raises(ValueError, match="invalid date"):
        normalize_date(value)


def test_decimal_and_identifier_standardization() -> None:
    assert parse_decimal(" 1234.50 ") == Decimal("1234.50")
    assert decimal_string(Decimal("1.005"), Decimal("0.01")) == "1.01"
    assert normalize_identifier(" cus-de-001 ") == "CUS-DE-001"


@pytest.mark.parametrize("value", ["1,234", "1,234.56", "1.234,56", "1 234.56"])
def test_ambiguous_decimal_formats_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="Ambiguous decimal"):
        parse_decimal(value)


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity", "not-a-number"])
def test_non_finite_and_malformed_decimals_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="decimal"):
        parse_decimal(value)


def test_non_finite_decimal_cannot_be_persisted() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        decimal_string(Decimal("NaN"), Decimal("0.01"))


def test_route_and_fact_domain_failures_produce_stable_reason_codes() -> None:
    route = {
        "route_id": " route-1 ",
        "origin_country_code": "Germany",
        "destination_country_code": "NLD",
        "transport_mode": " road ",
        "distance_km": "-1",
        "standard_transit_days": "1.5",
    }
    standardized_route, route_reasons = _standardize_dimension("routes", route)
    assert standardized_route["route_id"] == "ROUTE-1"
    assert standardized_route["origin_country_code"] == "DE"
    assert standardized_route["destination_country_code"] == "NL"
    assert standardized_route["transport_mode"] == "ROAD"
    assert standardized_route["distance_km"] == ""
    assert standardized_route["standard_transit_days"] == ""
    assert route_reasons == ["INVALID_ROUTE_DEFINITION"]

    shipment = {
        "shipment_id": "SHP-1",
        "shipment_date": "2025-01-01",
        "route_id": "ROUTE-1",
        "volume_m3": "0",
        "country_code": "DE",
        "customer_id": "CUS-1",
        "cost_center_id": "CC-1",
        "revenue_amount": "-1",
        "currency_code": "EUR",
    }
    standardized_shipment, shipment_reasons = _standardize_fact(
        "shipments", shipment, load_project_config()
    )
    assert standardized_shipment["revenue_amount"] == ""
    assert standardized_shipment["volume_m3"] == ""
    assert shipment_reasons == ["INVALID_FINANCIAL_VALUE", "INVALID_SHIPMENT_VOLUME"]

    cost = {
        "cost_id": "CST-1",
        "shipment_id": "SHP-1",
        "route_id": "ROUTE-1",
        "cost_center_id": "CC-1",
        "country_code": "DE",
        "posting_date": "2025-01-01",
        "cost_type": "tax",
        "amount": "-1",
        "currency_code": "EUR",
    }
    standardized_cost, cost_reasons = _standardize_fact(
        "operational_costs", cost, load_project_config()
    )
    assert standardized_cost["amount"] == ""
    assert standardized_cost["cost_type"] == "TAX"
    assert cost_reasons == ["INVALID_FINANCIAL_VALUE", "INVALID_COST_TYPE"]
