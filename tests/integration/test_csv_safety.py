from __future__ import annotations

from pathlib import Path

import pytest

from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from datalibra.storage.local import write_spreadsheet_csv_export
from tests.helpers import read_rows, refresh_manifest, write_rows


@pytest.mark.integration
def test_internal_csvs_preserve_canonical_values_and_explicit_export_is_safe(
    tmp_path: Path,
) -> None:
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
    assert quarantined_customer["customer_name"].startswith("=")
    assert silver_invoice["source_updated_at"] == "=2+2"

    export_path = tmp_path / "customer-export.csv"
    write_spreadsheet_csv_export(export_path, [quarantined_customer])
    exported = read_rows(export_path)[0]
    assert exported["customer_name"].startswith("'=")


@pytest.mark.integration
@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_formula_leading_identifier_remains_canonical_through_reconciliation(
    tmp_path: Path, prefix: str
) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    customers = read_rows(batch / "customers.csv")
    original_id = customers[0]["customer_id"]
    replacement_id = f"{prefix}{original_id}"
    customers[0]["customer_id"] = f"  {replacement_id.lower()}  "
    shipments = read_rows(batch / "shipments.csv")
    invoices = read_rows(batch / "invoices.csv")
    for row in [*shipments, *invoices]:
        if row["customer_id"] == original_id:
            row["customer_id"] = f" {replacement_id.lower()} "
    write_rows(batch / "customers.csv", "customers", customers)
    write_rows(batch / "shipments.csv", "shipments", shipments)
    write_rows(batch / "invoices.csv", "invoices", invoices)
    refresh_manifest(batch)
    output = tmp_path / "output"

    summary = process_batch(batch, output)

    silver_customer = next(
        row
        for row in read_rows(output / "silver" / "customers.csv")
        if row["customer_id"] == replacement_id
    )
    assert summary.status == "success"
    assert silver_customer["customer_id"] == replacement_id


@pytest.mark.integration
def test_csv_round_trip_preserves_quotes_newlines_unicode_and_name_whitespace(
    tmp_path: Path,
) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    customers = read_rows(batch / "customers.csv")
    special_name = '  "İstanbul, Avrupa"\n第二行  '
    customers[0]["customer_name"] = special_name
    write_rows(batch / "customers.csv", "customers", customers)
    refresh_manifest(batch)
    output = tmp_path / "output"

    summary = process_batch(batch, output)

    committed = read_rows(output / "silver" / "customers.csv")
    assert summary.status == "success"
    assert committed[0]["customer_name"] == special_name
