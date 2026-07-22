from __future__ import annotations

import re
from pathlib import Path

import pytest

from datalibra.generators import generate_scenario
from datalibra.generators.synthetic import FIELDS
from datalibra.silver import process_batch
from tests.helpers import read_rows


@pytest.mark.contract
def test_source_headers_are_exact_and_complete(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    for dataset, fields in FIELDS.items():
        header = (batch / f"{dataset}.csv").read_text(encoding="utf-8").splitlines()[0]
        assert tuple(header.split(",")) == fields


@pytest.mark.contract
def test_silver_invoice_contract_uses_iso_and_fixed_scale_values(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"
    process_batch(batch, output)
    rows = read_rows(output / "silver" / "invoices.csv")

    assert {row["country_code"] for row in rows} == {"DE", "NL", "FR", "GB", "TR"}
    assert {row["currency_code"] for row in rows} == {"EUR", "GBP", "TRY"}
    assert all(re.fullmatch(r"2025-\d{2}-\d{2}", row["invoice_date"]) for row in rows)
    assert all(re.fullmatch(r"\d+\.\d{2}", row["revenue_amount"]) for row in rows)
    assert all(re.fullmatch(r"\d+\.\d{6}", row["fx_rate_to_eur"]) for row in rows)
    assert all(re.fullmatch(r"\d+\.\d{2}", row["amount_eur"]) for row in rows)
    assert all(row["_batch_id"] == "slice001-healthy" for row in rows)


@pytest.mark.contract
def test_quality_result_contract_records_passes_and_failures(tmp_path: Path) -> None:
    batch = generate_scenario("duplicate_invoices", tmp_path / "input")
    output = tmp_path / "output"
    process_batch(batch, output)
    rows = read_rows(output / "quality" / "quality_results.csv")
    duplicate = next(
        row
        for row in rows
        if row["rule_name"] == "DUPLICATE_INVOICE" and row["affected_dataset"] == "invoices"
    )

    assert duplicate["validation_status"] == "FAIL"
    assert duplicate["failure_reason"] == "DUPLICATE_INVOICE"
    assert duplicate["failed_row_count"] == "12"
    assert any(row["validation_status"] == "PASS" for row in rows)
