from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from datalibra.domain.errors import ArtifactIntegrityError
from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from datalibra.storage.local import LocalCsvStorage
from tests.helpers import read_rows, refresh_manifest, write_rows


def _copy_with_unique_invoices(source: Path, destination: Path, batch_id: str) -> Path:
    shutil.copytree(source, destination)
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["batch_id"] = batch_id
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    invoices_path = destination / "invoices.csv"
    invoices = read_rows(invoices_path)
    for row in invoices:
        row["invoice_id"] = f"{batch_id}-{row['invoice_id']}"
    write_rows(invoices_path, "invoices", invoices)
    refresh_manifest(destination)
    return destination


@pytest.mark.integration
@pytest.mark.parametrize(
    ("artifact", "relative_path"),
    [
        ("silver", Path("silver/invoices.csv")),
        ("claim_manifest", Path("claims/invoices/slice001-healthy.csv")),
        ("claim_aggregate", Path("claims/invoices.csv")),
        ("summary", Path("runs/slice001-healthy.json")),
        ("reconciliation", Path("reconciliation/slice001-healthy.json")),
        ("quality", Path("quality/quality_results.csv")),
    ],
)
def test_noop_replay_rebuilds_missing_required_artifact(
    tmp_path: Path, artifact: str, relative_path: Path
) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"
    process_batch(batch, output)
    target = output / relative_path
    target.unlink()

    rebuilt = process_batch(batch, output)

    assert artifact
    assert rebuilt.status == "success"
    assert target.exists()
    assert len(read_rows(output / "silver" / "invoices.csv")) == 720


@pytest.mark.integration
def test_noop_replay_rebuilds_missing_expected_quarantine(tmp_path: Path) -> None:
    batch = generate_scenario("duplicate_invoices", tmp_path / "input")
    output = tmp_path / "output"
    process_batch(batch, output)
    quarantine_path = output / "quarantine" / "invoices.csv"
    quarantine_path.unlink()

    rebuilt = process_batch(batch, output)

    assert rebuilt.status == "quality_failed"
    assert len(read_rows(quarantine_path)) == 12


@pytest.mark.integration
def test_absent_empty_quarantine_is_legitimate_on_noop(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"
    process_batch(batch, output)
    empty_quarantine = output / "quarantine" / "countries.csv"
    if empty_quarantine.exists():
        empty_quarantine.unlink()

    replay = process_batch(batch, output)

    assert replay.status == "already_processed"
    assert not empty_quarantine.exists()


@pytest.mark.integration
def test_unrelated_batch_refuses_to_bless_damaged_prior_evidence(tmp_path: Path) -> None:
    first = generate_scenario("healthy", tmp_path / "first")
    second = _copy_with_unique_invoices(first, tmp_path / "second", "second")
    output = tmp_path / "output"
    process_batch(first, output)
    summary_path = output / "runs" / "slice001-healthy.json"
    summary_path.unlink()
    state_before = (output / "state" / "processed_batches.json").read_bytes()
    silver_before = (output / "silver" / "invoices.csv").read_bytes()

    with pytest.raises(ArtifactIntegrityError, match="PRIOR_ARTIFACT_INTEGRITY_FAILED"):
        process_batch(second, output)

    assert (output / "state" / "processed_batches.json").read_bytes() == state_before
    assert (output / "silver" / "invoices.csv").read_bytes() == silver_before


class EvidenceFaultStorage(LocalCsvStorage):
    def __init__(self, root: Path, fault: str) -> None:
        super().__init__(root)
        self.fault = fault

    def replace_batch_quality(self, batch_id: str, rows: list[dict[str, str]]) -> None:
        if self.fault != "quality":
            super().replace_batch_quality(batch_id, rows)

    def write_reconciliation(self, batch_id: str, value: dict[str, object]) -> None:
        if self.fault != "reconciliation":
            super().write_reconciliation(batch_id, value)

    def write_summary(self, batch_id: str, value: dict[str, object]) -> None:
        if self.fault != "summary":
            super().write_summary(batch_id, value)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("quality", "QUALITY_EVIDENCE_PUBLICATION_FAILED"),
        ("reconciliation", "RECONCILIATION_EVIDENCE_PUBLICATION_FAILED"),
        ("summary", "SUMMARY_EVIDENCE_PUBLICATION_FAILED"),
    ],
)
def test_evidence_publication_is_read_back_before_state(
    tmp_path: Path, fault: str, message: str
) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"

    with pytest.raises(ArtifactIntegrityError, match=message):
        process_batch(batch, output, storage=EvidenceFaultStorage(output, fault))

    assert not (output / "state" / "processed_batches.json").exists()
