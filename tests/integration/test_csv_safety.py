from __future__ import annotations

from pathlib import Path

import pytest

from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from tests.helpers import read_rows, refresh_manifest, write_rows


@pytest.mark.integration
def test_steward_facing_csvs_neutralize_formula_payloads(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    customers = read_rows(batch / "customers.csv")
    customers[0]["customer_name"] = '=HYPERLINK("https://example.invalid","open")'
    customers[0]["country_code"] = "XX"
    invoices = read_rows(batch / "invoices.csv")
    invoices[1]["source_updated_at"] = "=2+2"
    write_rows(batch / "customers.csv", "customers", customers)
    write_rows(batch / "invoices.csv", "invoices", invoices)
    refresh_manifest(batch)
    output = tmp_path / "output"

    process_batch(batch, output)

    bronze_customer = read_rows(next((output / "bronze" / "customers").glob("*.csv")))[0]
    quarantined_customer = read_rows(output / "quarantine" / "customers.csv")[0]
    silver_invoice = next(
        row
        for row in read_rows(output / "silver" / "invoices.csv")
        if row["invoice_id"] == invoices[1]["invoice_id"]
    )
    assert bronze_customer["customer_name"].startswith("=")
    assert quarantined_customer["customer_name"].startswith("'=")
    assert silver_invoice["source_updated_at"] == "'=2+2"
