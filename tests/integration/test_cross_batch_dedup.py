from __future__ import annotations

import json
import shutil
from decimal import Decimal
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


def _prefix_invoice_ids(batch: Path, prefix: str) -> None:
    invoices = read_rows(batch / "invoices.csv")
    for row in invoices:
        row["invoice_id"] = f"{prefix}{row['invoice_id']}"
    write_rows(batch / "invoices.csv", "invoices", invoices)
    refresh_manifest(batch)


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
    assert {row["_reason_codes"] for row in replay_quarantine} == {"CROSS_BATCH_DUPLICATE_INVOICE"}


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


@pytest.mark.integration
def test_explicit_arrival_sequence_survives_sorted_json_and_unrelated_batch(
    tmp_path: Path,
) -> None:
    zulu = generate_scenario("healthy", tmp_path / "zulu-source")
    zulu_manifest = json.loads((zulu / "manifest.json").read_text(encoding="utf-8"))
    zulu_manifest["batch_id"] = "zulu-first"
    (zulu / "manifest.json").write_text(
        json.dumps(zulu_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    alpha = _copy_as_batch(zulu, tmp_path / "alpha-source", "alpha-second")
    middle = _copy_as_batch(zulu, tmp_path / "middle-source", "middle-third")
    _prefix_invoice_ids(middle, "M-")
    output = tmp_path / "output"

    process_batch(zulu, output)
    process_batch(alpha, output)
    before = [
        row
        for row in read_rows(output / "silver" / "invoices.csv")
        if not row["invoice_id"].startswith("M-")
    ]
    before_bytes = json.dumps(before, sort_keys=True, separators=(",", ":")).encode()
    before_revenue = sum(Decimal(row["amount_eur"]) for row in before)

    process_batch(middle, output)

    after = [
        row
        for row in read_rows(output / "silver" / "invoices.csv")
        if not row["invoice_id"].startswith("M-")
    ]
    state = json.loads((output / "state" / "processed_batches.json").read_text(encoding="utf-8"))
    assert json.dumps(after, sort_keys=True, separators=(",", ":")).encode() == before_bytes
    assert sum(Decimal(row["amount_eur"]) for row in after) == before_revenue
    assert {row["_batch_id"] for row in after} == {"zulu-first"}
    assert state["batches"]["zulu-first"]["arrival_sequence"] == 1
    assert state["batches"]["alpha-second"]["arrival_sequence"] == 2
    assert state["batches"]["middle-third"]["arrival_sequence"] == 3
    assert list(state["batches"]) == ["alpha-second", "middle-third", "zulu-first"]


@pytest.mark.integration
def test_correcting_batch_preserves_arrival_sequence(tmp_path: Path) -> None:
    first = generate_scenario("healthy", tmp_path / "first")
    second = _copy_as_batch(first, tmp_path / "second", "second-arrival")
    output = tmp_path / "output"
    process_batch(first, output)
    process_batch(second, output)
    state_path = output / "state" / "processed_batches.json"
    before = json.loads(state_path.read_text(encoding="utf-8"))

    invoices = read_rows(second / "invoices.csv")
    invoices[0]["source_updated_at"] = "2026-07-23T01:02:03Z"
    write_rows(second / "invoices.csv", "invoices", invoices)
    refresh_manifest(second)
    process_batch(second, output)

    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert before["batches"]["second-arrival"]["arrival_sequence"] == 2
    assert after["batches"]["second-arrival"]["arrival_sequence"] == 2
    assert after["next_arrival_sequence"] == 3


@pytest.mark.integration
@pytest.mark.parametrize(
    ("first_id", "second_id"),
    [("zulu", "alpha"), ("alpha", "zulu")],
)
def test_processing_order_deterministically_selects_actual_first_arrival(
    tmp_path: Path, first_id: str, second_id: str
) -> None:
    source = generate_scenario("healthy", tmp_path / "source")
    first = _copy_as_batch(source, tmp_path / "first", first_id)
    second = _copy_as_batch(source, tmp_path / "second", second_id)
    output = tmp_path / "output"

    process_batch(first, output)
    process_batch(second, output)

    silver = read_rows(output / "silver" / "invoices.csv")
    assert {row["_batch_id"] for row in silver} == {first_id}
