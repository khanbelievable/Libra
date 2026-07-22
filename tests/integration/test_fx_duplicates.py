from __future__ import annotations

from pathlib import Path

import pytest

from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from tests.helpers import read_rows, refresh_manifest, write_rows


@pytest.mark.integration
def test_exact_duplicate_fx_row_is_deduplicated_deterministically(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    rates = read_rows(batch / "exchange_rates.csv")
    duplicate = rates[0].copy()
    rates.append(duplicate)
    write_rows(batch / "exchange_rates.csv", "exchange_rates", rates)
    refresh_manifest(batch)
    output = tmp_path / "output"

    summary = process_batch(batch, output)

    silver = read_rows(output / "silver" / "exchange_rates.csv")
    quarantine = read_rows(output / "quarantine" / "exchange_rates.csv")
    assert summary.status == "quality_failed"
    assert "EXCHANGE_RATE_UNIQUENESS" in summary.failed_rules
    assert len(silver) == 1095
    assert len(quarantine) == 1
    assert quarantine[0]["_reason_codes"] == "DUPLICATE_EXCHANGE_RATE"
    assert summary.trusted_invoice_revenue_eur == "916351.47"


@pytest.mark.integration
def test_conflicting_fx_rows_withhold_key_and_dependent_facts(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    invoices = read_rows(batch / "invoices.csv")
    target_invoice = next(row for row in invoices if row["currency_code"] == "GBP")
    rates = read_rows(batch / "exchange_rates.csv")
    original = next(
        row
        for row in rates
        if row["rate_date"] == target_invoice["invoice_date"] and row["currency_code"] == "GBP"
    )
    conflicting = original.copy()
    conflicting["rate_to_eur"] = "9.999999"
    rates.append(conflicting)
    write_rows(batch / "exchange_rates.csv", "exchange_rates", rates)
    refresh_manifest(batch)
    output = tmp_path / "output"

    summary = process_batch(batch, output)

    silver_rates = read_rows(output / "silver" / "exchange_rates.csv")
    quarantined_rates = read_rows(output / "quarantine" / "exchange_rates.csv")
    quarantined_invoices = read_rows(output / "quarantine" / "invoices.csv")
    assert summary.status == "quality_failed"
    assert "EXCHANGE_RATE_UNIQUENESS" in summary.failed_rules
    assert not any(
        row["rate_date"] == original["rate_date"] and row["currency_code"] == "GBP"
        for row in silver_rates
    )
    conflicting_quarantine = [
        row
        for row in quarantined_rates
        if row["rate_date"] == original["rate_date"] and row["currency_code"] == "GBP"
    ]
    assert len(conflicting_quarantine) == 2
    assert all(
        "CONFLICTING_EXCHANGE_RATE" in row["_reason_codes"] for row in conflicting_quarantine
    )
    affected = next(
        row for row in quarantined_invoices if row["invoice_id"] == target_invoice["invoice_id"]
    )
    assert affected["_reason_codes"] == "CONFLICTING_EXCHANGE_RATE_REFERENCE"
    assert affected["amount_eur"] == ""
