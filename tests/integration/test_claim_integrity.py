from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from datalibra.domain.errors import ClaimsIntegrityError, StateIntegrityError
from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from datalibra.storage.local import LocalCsvStorage, write_csv_atomic
from tests.helpers import read_rows, refresh_manifest, write_rows


def _copy_with_unique_invoices(source: Path, destination: Path, batch_id: str) -> Path:
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


def _corrupt_rows(rows: list[dict[str, str]], fault: str) -> list[dict[str, str]]:
    if fault == "empty":
        return []
    if fault == "truncated":
        return rows[: len(rows) // 2]
    if fault == "altered_amount":
        changed = [dict(row) for row in rows]
        changed[0]["amount_eur"] = "999999.99"
        return changed
    if fault == "altered_owner":
        changed = [dict(row) for row in rows]
        changed[0]["_batch_id"] = "forged-owner"
        return changed
    if fault == "duplicated":
        return [*rows, dict(rows[0])]
    raise AssertionError(f"Unsupported fault: {fault}")


@pytest.mark.integration
@pytest.mark.parametrize(
    "fault",
    ["deleted", "empty", "truncated", "altered_amount", "altered_owner", "duplicated"],
)
def test_damaged_batch_claim_manifest_fails_closed_without_shrinking_silver(
    tmp_path: Path, fault: str
) -> None:
    first = generate_scenario("healthy", tmp_path / "first")
    second = _copy_with_unique_invoices(first, tmp_path / "second", "second")
    output = tmp_path / "output"
    process_batch(first, output)
    manifest_path = output / "claims" / "invoices" / "slice001-healthy.csv"
    state_path = output / "state" / "processed_batches.json"
    silver_path = output / "silver" / "invoices.csv"
    state_before = state_path.read_bytes()
    silver_before = silver_path.read_bytes()

    if fault == "deleted":
        manifest_path.unlink()
    else:
        rows = read_rows(manifest_path)
        write_csv_atomic(manifest_path, _corrupt_rows(rows, fault))

    with pytest.raises(ClaimsIntegrityError, match="CLAIM_MANIFEST_INTEGRITY_FAILED"):
        process_batch(second, output)

    assert state_path.read_bytes() == state_before
    assert silver_path.read_bytes() == silver_before
    assert len(read_rows(silver_path)) == 720


@pytest.mark.integration
@pytest.mark.parametrize(
    "fault",
    ["deleted", "empty", "truncated", "altered_amount", "duplicated", "stale"],
)
def test_damaged_aggregate_is_rebuilt_only_from_attested_batch_manifests(
    tmp_path: Path, fault: str
) -> None:
    first = generate_scenario("healthy", tmp_path / "first")
    second = _copy_with_unique_invoices(first, tmp_path / "second", "second")
    output = tmp_path / "output"
    process_batch(first, output)
    aggregate_path = output / "claims" / "invoices.csv"
    original_claims = read_rows(aggregate_path)

    if fault == "deleted":
        aggregate_path.unlink()
    elif fault == "stale":
        write_csv_atomic(aggregate_path, original_claims[:100])
    else:
        write_csv_atomic(aggregate_path, _corrupt_rows(original_claims, fault))

    summary = process_batch(second, output)

    rebuilt_claims = read_rows(aggregate_path)
    silver = read_rows(output / "silver" / "invoices.csv")
    assert summary.status == "success"
    assert len(rebuilt_claims) == 1440
    assert len(silver) == 1440
    assert sum(row["_batch_id"] == "slice001-healthy" for row in silver) == 720


@pytest.mark.integration
def test_missing_processed_state_claim_attestation_is_rejected(tmp_path: Path) -> None:
    first = generate_scenario("healthy", tmp_path / "first")
    second = _copy_with_unique_invoices(first, tmp_path / "second", "second")
    output = tmp_path / "output"
    process_batch(first, output)
    state_path = output / "state" / "processed_batches.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["batches"]["slice001-healthy"].pop("invoice_claim_attestation")
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    silver_before = (output / "silver" / "invoices.csv").read_bytes()

    with pytest.raises(StateIntegrityError, match="STATE_CLAIM_ATTESTATION_MISSING"):
        process_batch(second, output)

    assert (output / "silver" / "invoices.csv").read_bytes() == silver_before


class TruncatingManifestStorage(LocalCsvStorage):
    def replace_batch_claim_manifest(
        self, dataset: str, batch_id: str, rows: list[dict[str, str]]
    ) -> None:
        super().replace_batch_claim_manifest(dataset, batch_id, rows)
        path = self.root / "claims" / dataset / f"{batch_id}.csv"
        write_csv_atomic(path, list(rows)[: len(rows) // 2])


@pytest.mark.integration
def test_current_manifest_publication_is_verified_before_silver(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"

    with pytest.raises(ClaimsIntegrityError, match="CLAIM_MANIFEST_PUBLICATION_FAILED"):
        process_batch(batch, output, storage=TruncatingManifestStorage(output))

    assert not (output / "silver" / "invoices.csv").exists()
    assert not (output / "state" / "processed_batches.json").exists()
