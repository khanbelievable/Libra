from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from tests.helpers import read_rows, refresh_manifest, write_rows


def _copy_as_batch(source: Path, destination: Path, batch_id: str) -> Path:
    shutil.copytree(source, destination)
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["batch_id"] = batch_id
    manifest["scenario"] = "cross_batch_test"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination


@pytest.mark.integration
def test_exact_cross_batch_resend_preserves_original_ownership(tmp_path: Path) -> None:
    first_batch = generate_scenario("healthy", tmp_path / "input-a")
    replay_batch = _copy_as_batch(first_batch, tmp_path / "input-b", "delivery-replay")
    output = tmp_path / "output"

    original = process_batch(first_batch, output)
    replay = process_batch(replay_batch, output)
    repeated = process_batch(replay_batch, output)

    silver = read_rows(output / "silver" / "invoices.csv")
    replay_quarantine = [
        row
        for row in read_rows(output / "quarantine" / "invoices.csv")
        if row["_batch_id"] == "delivery-replay"
    ]
    assert original.trusted_invoice_revenue_eur == "916351.47"
    assert replay.status == "quality_failed"
    assert replay.silver_rows["invoices"] == 0
    assert replay.trusted_invoice_revenue_eur == "0.00"
    assert repeated.status == "already_processed"
    assert len(silver) == 720
    assert len(replay_quarantine) == 720
    assert {row["_reason_codes"] for row in replay_quarantine} == {
        "CROSS_BATCH_DUPLICATE_INVOICE"
    }


@pytest.mark.integration
def test_conflicting_claims_are_withheld_and_batch_correction_is_scoped(tmp_path: Path) -> None:
    first_batch = generate_scenario("healthy", tmp_path / "input-a")
    second_batch = _copy_as_batch(first_batch, tmp_path / "input-b", "independent-delivery")
    second_invoices = read_rows(second_batch / "invoices.csv")
    for row in second_invoices:
        row["invoice_id"] = f"B-{row['invoice_id']}"
    first_invoice_id = read_rows(first_batch / "invoices.csv")[0]["invoice_id"]
    second_invoices[0]["invoice_id"] = first_invoice_id
    second_invoices[0]["revenue_amount"] = "9999.00"
    write_rows(second_batch / "invoices.csv", "invoices", second_invoices)
    refresh_manifest(second_batch)
    output = tmp_path / "output"

    process_batch(first_batch, output)
    conflict = process_batch(second_batch, output)

    conflicted_silver = read_rows(output / "silver" / "invoices.csv")
    conflicted_quarantine = [
        row
        for row in read_rows(output / "quarantine" / "invoices.csv")
        if row["invoice_id"] == first_invoice_id
    ]
    assert conflict.status == "quality_failed"
    assert len(conflicted_silver) == 1438
    assert not any(row["invoice_id"] == first_invoice_id for row in conflicted_silver)
    assert len(conflicted_quarantine) == 2
    assert {row["_reason_codes"] for row in conflicted_quarantine} == {
        "CONFLICTING_DUPLICATE_INVOICE"
    }

    second_invoices[0]["invoice_id"] = "B-INV-2025-000001"
    write_rows(second_batch / "invoices.csv", "invoices", second_invoices)
    refresh_manifest(second_batch)
    corrected = process_batch(second_batch, output)

    corrected_silver = read_rows(output / "silver" / "invoices.csv")
    remaining_conflicts = [
        row
        for row in read_rows(output / "quarantine" / "invoices.csv")
        if row["_reason_codes"] == "CONFLICTING_DUPLICATE_INVOICE"
    ]
    assert corrected.status == "success"
    assert corrected.silver_rows["invoices"] == 720
    assert len(corrected_silver) == 1440
    assert any(row["invoice_id"] == first_invoice_id for row in corrected_silver)
    assert any(row["invoice_id"] == "B-INV-2025-000001" for row in corrected_silver)
    assert remaining_conflicts == []

    first_invoices = read_rows(first_batch / "invoices.csv")
    first_invoices[1]["revenue_amount"] = "1234.56"
    write_rows(first_batch / "invoices.csv", "invoices", first_invoices)
    refresh_manifest(first_batch)
    process_batch(first_batch, output)
    final_silver = read_rows(output / "silver" / "invoices.csv")
    assert len(final_silver) == 1440
    assert sum(row["_batch_id"] == "independent-delivery" for row in final_silver) == 720
