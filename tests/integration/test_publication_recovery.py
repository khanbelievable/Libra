from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

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
    invoices = read_rows(destination / "invoices.csv")
    for row in invoices:
        row["invoice_id"] = f"{batch_id}-{row['invoice_id']}"
    write_rows(destination / "invoices.csv", "invoices", invoices)
    refresh_manifest(destination)
    return destination


class BoundaryCrashStorage(LocalCsvStorage):
    def __init__(self, root: Path, boundary: str) -> None:
        super().__init__(root)
        self.boundary = boundary
        self.failed = False

    def _trip(self, boundary: str) -> None:
        if self.boundary == boundary and not self.failed:
            self.failed = True
            raise OSError(f"simulated crash after {boundary}")

    def replace_batch_claim_manifest(
        self, dataset: str, batch_id: str, rows: Sequence[dict[str, str]]
    ) -> None:
        super().replace_batch_claim_manifest(dataset, batch_id, rows)
        self._trip("claim_manifest")

    def replace_all_claims(self, dataset: str, rows: Sequence[dict[str, str]]) -> None:
        super().replace_all_claims(dataset, rows)
        self._trip("claim_aggregate")

    def replace_all_silver(
        self,
        dataset: str,
        rows: Sequence[dict[str, str]],
        business_key: tuple[str, ...],
    ) -> None:
        super().replace_all_silver(dataset, rows, business_key)
        if dataset == "invoices":
            self._trip("invoice_silver")

    def replace_batch_quality(self, batch_id: str, rows: Sequence[dict[str, str]]) -> None:
        super().replace_batch_quality(batch_id, rows)
        self._trip("quality")

    def write_reconciliation(self, batch_id: str, value: dict[str, Any]) -> None:
        super().write_reconciliation(batch_id, value)
        self._trip("reconciliation")

    def write_summary(self, batch_id: str, value: dict[str, Any]) -> None:
        super().write_summary(batch_id, value)
        self._trip("summary")


@pytest.mark.integration
@pytest.mark.parametrize(
    "boundary",
    [
        "claim_manifest",
        "claim_aggregate",
        "invoice_silver",
        "quality",
        "reconciliation",
        "summary",
    ],
)
def test_retry_converges_after_each_attested_publication_boundary(
    tmp_path: Path, boundary: str
) -> None:
    first = generate_scenario("healthy", tmp_path / "first")
    second = _copy_with_unique_invoices(first, tmp_path / "second", "second")
    output = tmp_path / "output"
    process_batch(first, output)
    storage = BoundaryCrashStorage(output, boundary)

    with pytest.raises(OSError, match=f"after {boundary}"):
        process_batch(second, output, storage=storage)

    interrupted_state = json.loads(
        (output / "state" / "processed_batches.json").read_text(encoding="utf-8")
    )
    assert set(interrupted_state["batches"]) == {"slice001-healthy"}
    assert (output / "state" / "inflight.json").is_file()

    recovered = process_batch(second, output, storage=storage)

    state = json.loads((output / "state" / "processed_batches.json").read_text(encoding="utf-8"))
    silver = read_rows(output / "silver" / "invoices.csv")
    assert recovered.status == "success"
    assert len(silver) == 1440
    assert sum(row["_batch_id"] == "slice001-healthy" for row in silver) == 720
    assert sum(row["_batch_id"] == "second" for row in silver) == 720
    assert state["batches"]["slice001-healthy"]["arrival_sequence"] == 1
    assert state["batches"]["second"]["arrival_sequence"] == 2
    assert not (output / "state" / "inflight.json").exists()
