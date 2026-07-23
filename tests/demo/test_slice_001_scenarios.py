from __future__ import annotations

from pathlib import Path

import pytest

from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from tests.helpers import read_rows

EXPECTED = {
    "healthy": {
        "status": "success",
        "bronze_invoices": 720,
        "silver_invoices": 720,
        "quarantine": {
            "shipments": 0,
            "invoices": 0,
            "budgets": 0,
            "operational_costs": 0,
        },
        "failed_rules": (),
        "revenue": "916351.47",
    },
    "duplicate_invoices": {
        "status": "quality_failed",
        "bronze_invoices": 732,
        "silver_invoices": 720,
        "quarantine": {
            "shipments": 0,
            "invoices": 12,
            "budgets": 0,
            "operational_costs": 0,
        },
        "failed_rules": ("DUPLICATE_INVOICE",),
        "revenue": "916351.47",
    },
    "missing_gbp_fx": {
        "status": "quality_failed",
        "bronze_invoices": 720,
        "silver_invoices": 708,
        "quarantine": {
            "shipments": 12,
            "invoices": 12,
            "budgets": 2,
            "operational_costs": 48,
        },
        "failed_rules": ("EXCHANGE_RATE_EXISTS",),
        "revenue": "900446.34",
    },
    "incomplete_germany": {
        "status": "quality_failed",
        "bronze_invoices": 619,
        "silver_invoices": 576,
        "quarantine": {
            "shipments": 0,
            "invoices": 43,
            "budgets": 0,
            "operational_costs": 0,
        },
        "failed_rules": ("INVOICE_COUNTRY_VOLUME",),
        "revenue": "697854.41",
    },
}


@pytest.mark.demo
@pytest.mark.parametrize("scenario", EXPECTED)
def test_documented_scenario_evidence(scenario: str, tmp_path: Path) -> None:
    expected = EXPECTED[scenario]
    batch = generate_scenario(scenario, tmp_path / "input")
    output = tmp_path / "output"
    summary = process_batch(batch, output)

    assert summary.status == expected["status"]
    assert summary.bronze_rows["invoices"] == expected["bronze_invoices"]
    assert summary.silver_rows["invoices"] == expected["silver_invoices"]
    assert summary.quarantine_rows == expected["quarantine"]
    assert summary.failed_rules == expected["failed_rules"]
    assert summary.trusted_invoice_revenue_eur == expected["revenue"]
    assert all(
        row["validation_status"] == "PASS"
        for row in read_rows(output / "quality" / "quality_results.csv")
        if row["rule_name"].startswith("SOURCE_TARGET_")
    )


@pytest.mark.demo
def test_missing_fx_rows_have_no_trusted_eur_value(tmp_path: Path) -> None:
    batch = generate_scenario("missing_gbp_fx", tmp_path / "input")
    output = tmp_path / "output"
    process_batch(batch, output)
    quarantined = read_rows(output / "quarantine" / "invoices.csv")

    assert len(quarantined) == 12
    assert all(row["_reason_codes"] == "MISSING_EXCHANGE_RATE" for row in quarantined)
    assert all(row["amount_eur"] == "" for row in quarantined)
    assert all(row["fx_rate_to_eur"] == "" for row in quarantined)
