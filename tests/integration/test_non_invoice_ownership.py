from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from datalibra.domain.errors import CrossBatchCollisionError
from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from tests.helpers import read_rows, refresh_manifest, write_rows


def _copy_batch(source: Path, destination: Path, batch_id: str) -> Path:
    shutil.copytree(source, destination)
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["batch_id"] = batch_id
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    invoices = read_rows(destination / "invoices.csv")
    for row in invoices:
        row["invoice_id"] = f"{batch_id}-{row['invoice_id']}"
    write_rows(destination / "invoices.csv", "invoices", invoices)
    refresh_manifest(destination)
    return destination


@pytest.mark.integration
def test_exact_non_invoice_financial_replay_retains_first_owner(tmp_path: Path) -> None:
    first = generate_scenario("healthy", tmp_path / "first")
    second = _copy_batch(first, tmp_path / "second", "second")
    output = tmp_path / "output"

    process_batch(first, output)
    summary = process_batch(second, output)

    shipments = read_rows(output / "silver" / "shipments.csv")
    budgets = read_rows(output / "silver" / "budgets.csv")
    quarantined_shipments = [
        row
        for row in read_rows(output / "quarantine" / "shipments.csv")
        if row["_batch_id"] == "second"
    ]
    quarantined_budgets = [
        row
        for row in read_rows(output / "quarantine" / "budgets.csv")
        if row["_batch_id"] == "second"
    ]
    assert summary.status == "success"
    assert {row["_batch_id"] for row in shipments} == {"slice001-healthy"}
    assert {row["_batch_id"] for row in budgets} == {"slice001-healthy"}
    assert len(quarantined_shipments) == 720
    assert len(quarantined_budgets) == 120
    assert {row["_reason_codes"] for row in quarantined_shipments} == {
        "CROSS_BATCH_DUPLICATE_RECORD"
    }


@pytest.mark.integration
@pytest.mark.parametrize(
    ("dataset", "amount_field"),
    [("shipments", "revenue_amount"), ("budgets", "budget_amount")],
)
def test_conflicting_non_invoice_financial_collision_fails_before_overwrite(
    tmp_path: Path, dataset: str, amount_field: str
) -> None:
    first = generate_scenario("healthy", tmp_path / "first")
    second = _copy_batch(first, tmp_path / "second", "second")
    rows = read_rows(second / f"{dataset}.csv")
    rows[0][amount_field] = "99999.00"
    write_rows(second / f"{dataset}.csv", dataset, rows)
    refresh_manifest(second)
    output = tmp_path / "output"
    process_batch(first, output)
    state_before = (output / "state" / "processed_batches.json").read_bytes()
    silver_before = (output / "silver" / f"{dataset}.csv").read_bytes()

    with pytest.raises(CrossBatchCollisionError, match="CROSS_BATCH_FINANCIAL_COLLISION"):
        process_batch(second, output)

    assert (output / "state" / "processed_batches.json").read_bytes() == state_before
    assert (output / "silver" / f"{dataset}.csv").read_bytes() == silver_before
