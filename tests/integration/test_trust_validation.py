from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from tests.helpers import read_rows, refresh_manifest, write_rows


def _quality_rows(output: Path, rule: str) -> list[dict[str, str]]:
    return [
        row
        for row in read_rows(output / "quality" / "quality_results.csv")
        if row["rule_name"] == rule
    ]


@pytest.mark.integration
@pytest.mark.parametrize("invalid_rate", ["0", "-1", "NaN", "Infinity", "-Infinity", "malformed"])
def test_invalid_gbp_rate_and_dependent_invoice_are_quarantined(
    invalid_rate: str, tmp_path: Path
) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    invoices = read_rows(batch / "invoices.csv")
    target = next(row for row in invoices if row["currency_code"] == "GBP")
    rates = read_rows(batch / "exchange_rates.csv")
    target_rate = next(
        row
        for row in rates
        if row["currency_code"] == "GBP" and row["rate_date"] == target["invoice_date"]
    )
    target_rate["rate_to_eur"] = invalid_rate
    write_rows(batch / "exchange_rates.csv", "exchange_rates", rates)
    refresh_manifest(batch)
    output = tmp_path / "output"

    summary = process_batch(batch, output)

    quarantined_rates = read_rows(output / "quarantine" / "exchange_rates.csv")
    quarantined_invoices = read_rows(output / "quarantine" / "invoices.csv")
    silver_invoices = read_rows(output / "silver" / "invoices.csv")
    assert summary.status == "quality_failed"
    assert "VALID_EXCHANGE_RATES" in summary.failed_rules
    assert target_rate["rate_date"] in {row["rate_date"] for row in quarantined_rates}
    assert all(row["_reason_codes"] == "INVALID_EXCHANGE_RATE" for row in quarantined_rates)
    affected = next(
        row for row in quarantined_invoices if row["invoice_id"] == target["invoice_id"]
    )
    assert "INVALID_EXCHANGE_RATE_REFERENCE" in affected["_reason_codes"]
    assert affected["amount_eur"] == ""
    assert target["invoice_id"] not in {row["invoice_id"] for row in silver_invoices}
    assert any(
        row["validation_status"] == "FAIL" for row in _quality_rows(output, "VALID_EXCHANGE_RATES")
    )
    assert Decimal(summary.trusted_invoice_revenue_eur).is_finite()


@pytest.mark.integration
@pytest.mark.parametrize(
    "invalid_amount", ["NaN", "sNaN", "Infinity", "-Infinity", "malformed", "-1.00"]
)
def test_invalid_invoice_amount_never_enters_silver(invalid_amount: str, tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    invoices = read_rows(batch / "invoices.csv")
    target_id = invoices[0]["invoice_id"]
    invoices[0]["revenue_amount"] = invalid_amount
    write_rows(batch / "invoices.csv", "invoices", invoices)
    refresh_manifest(batch)
    output = tmp_path / "output"

    summary = process_batch(batch, output)

    quarantine = read_rows(output / "quarantine" / "invoices.csv")
    silver = read_rows(output / "silver" / "invoices.csv")
    target = next(row for row in quarantine if row["invoice_id"] == target_id)
    assert summary.status == "quality_failed"
    assert "FINITE_FINANCIAL_VALUES" in summary.failed_rules
    assert "INVALID_FINANCIAL_VALUE" in target["_reason_codes"]
    assert target["amount_eur"] == ""
    assert target_id not in {row["invoice_id"] for row in silver}
    assert Decimal(summary.trusted_invoice_revenue_eur).is_finite()


@pytest.mark.integration
def test_negative_budget_is_quarantined_but_zero_revenue_is_valid(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    budgets = read_rows(batch / "budgets.csv")
    budgets[0]["budget_amount"] = "-0.01"
    write_rows(batch / "budgets.csv", "budgets", budgets)
    invoices = read_rows(batch / "invoices.csv")
    zero_invoice_id = invoices[0]["invoice_id"]
    invoices[0]["revenue_amount"] = "0.00"
    write_rows(batch / "invoices.csv", "invoices", invoices)
    refresh_manifest(batch)
    output = tmp_path / "output"

    summary = process_batch(batch, output)

    budget_quarantine = read_rows(output / "quarantine" / "budgets.csv")
    invoice_silver = read_rows(output / "silver" / "invoices.csv")
    assert summary.status == "quality_failed"
    assert budget_quarantine[0]["_reason_codes"] == "INVALID_FINANCIAL_VALUE"
    assert (
        next(row for row in invoice_silver if row["invoice_id"] == zero_invoice_id)["amount_eur"]
        == "0.00"
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("field", "invalid_value", "expected_reason"),
    [
        ("country_code", "XX", "UNKNOWN_COUNTRY_CODE"),
        ("currency_code", "XXX", "UNKNOWN_CURRENCY_CODE"),
        ("customer_id", "CUS-UNKNOWN", "UNKNOWN_CUSTOMER_ID"),
        ("cost_center_id", "CC-UNKNOWN", "UNKNOWN_COST_CENTER_ID"),
        ("shipment_id", "SHP-UNKNOWN", "UNKNOWN_SHIPMENT_ID"),
    ],
)
def test_unknown_invoice_references_are_quarantined(
    field: str, invalid_value: str, expected_reason: str, tmp_path: Path
) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    invoices = read_rows(batch / "invoices.csv")
    target_id = invoices[0]["invoice_id"]
    invoices[0][field] = invalid_value
    write_rows(batch / "invoices.csv", "invoices", invoices)
    refresh_manifest(batch)
    output = tmp_path / "output"

    summary = process_batch(batch, output)

    target = next(
        row
        for row in read_rows(output / "quarantine" / "invoices.csv")
        if row["invoice_id"] == target_id
    )
    assert summary.status == "quality_failed"
    assert "REFERENTIAL_INTEGRITY" in summary.failed_rules
    assert expected_reason in target["_reason_codes"]
    assert target_id not in {
        row["invoice_id"] for row in read_rows(output / "silver" / "invoices.csv")
    }


@pytest.mark.integration
@pytest.mark.parametrize(
    ("dataset", "field", "invalid_value", "expected_reason"),
    [
        ("countries", "default_currency", "XXX", "UNKNOWN_CURRENCY_CODE"),
        ("customers", "country_code", "XX", "UNKNOWN_COUNTRY_CODE"),
        ("cost_centers", "country_code", "XX", "UNKNOWN_COUNTRY_CODE"),
        ("exchange_rates", "currency_code", "XXX", "UNKNOWN_CURRENCY_CODE"),
    ],
)
def test_master_reference_integrity_is_enforced(
    dataset: str,
    field: str,
    invalid_value: str,
    expected_reason: str,
    tmp_path: Path,
) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    rows = read_rows(batch / f"{dataset}.csv")
    rows[0][field] = invalid_value
    write_rows(batch / f"{dataset}.csv", dataset, rows)
    refresh_manifest(batch)
    output = tmp_path / "output"

    summary = process_batch(batch, output)

    quarantine = read_rows(output / "quarantine" / f"{dataset}.csv")
    assert summary.status == "quality_failed"
    assert "REFERENTIAL_INTEGRITY" in summary.failed_rules
    assert expected_reason in quarantine[0]["_reason_codes"]
