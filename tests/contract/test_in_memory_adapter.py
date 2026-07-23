from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from datalibra.storage.base import PipelineStorage


class InMemoryStorage:
    """Independent contract fixture with no filesystem persistence."""

    def __init__(self) -> None:
        self.bronze: dict[tuple[str, str, str], list[dict[str, str]]] = {}
        self.silver: dict[str, list[dict[str, str]]] = {}
        self.quarantine: dict[str, list[dict[str, str]]] = {}
        self.quality: list[dict[str, str]] = []
        self.claims: dict[str, list[dict[str, str]]] = {}
        self.state: dict[str, Any] = {
            "batches": {},
            "latest_successful_refresh_timestamp": None,
        }
        self.reconciliation: dict[str, dict[str, Any]] = {}
        self.summaries: dict[str, dict[str, Any]] = {}

    def write_bronze(
        self,
        dataset: str,
        batch_id: str,
        fingerprint: str,
        rows: Sequence[dict[str, str]],
    ) -> None:
        self.bronze[(dataset, batch_id, fingerprint)] = deepcopy(list(rows))

    def replace_batch_and_merge_silver(
        self,
        dataset: str,
        batch_id: str,
        rows: Sequence[dict[str, str]],
        business_key: tuple[str, ...],
    ) -> None:
        retained = [row for row in self.silver.get(dataset, []) if row.get("_batch_id") != batch_id]
        merged = {tuple(row[field] for field in business_key): row for row in retained}
        merged.update({tuple(row[field] for field in business_key): dict(row) for row in rows})
        self.silver[dataset] = [deepcopy(merged[key]) for key in sorted(merged)]

    def replace_all_silver(
        self,
        dataset: str,
        rows: Sequence[dict[str, str]],
        business_key: tuple[str, ...],
    ) -> None:
        self.silver[dataset] = sorted(
            deepcopy(list(rows)), key=lambda row: tuple(row[field] for field in business_key)
        )

    def replace_batch_quarantine(
        self, dataset: str, batch_id: str, rows: Sequence[dict[str, str]]
    ) -> None:
        retained = [
            row for row in self.quarantine.get(dataset, []) if row.get("_batch_id") != batch_id
        ]
        self.quarantine[dataset] = [*retained, *deepcopy(list(rows))]

    def replace_batch_quality(self, batch_id: str, rows: Sequence[dict[str, str]]) -> None:
        retained = [row for row in self.quality if row.get("batch_id") != batch_id]
        self.quality = [*retained, *deepcopy(list(rows))]

    def replace_batch_claim_manifest(
        self, dataset: str, batch_id: str, rows: Sequence[dict[str, str]]
    ) -> None:
        self.claims[f"{dataset}/{batch_id}"] = deepcopy(list(rows))

    def read_batch_claim_manifest(self, dataset: str, batch_id: str) -> list[dict[str, str]]:
        return deepcopy(self.claims.get(f"{dataset}/{batch_id}", []))

    def replace_all_claims(self, dataset: str, rows: Sequence[dict[str, str]]) -> None:
        self.claims[dataset] = deepcopy(list(rows))

    def read_claims(self, dataset: str) -> list[dict[str, str]]:
        return deepcopy(self.claims.get(dataset, []))

    def replace_dedup_quarantine(
        self,
        dataset: str,
        rows: Sequence[dict[str, str]],
        reason_codes: frozenset[str],
    ) -> None:
        retained = [
            row
            for row in self.quarantine.get(dataset, [])
            if not reason_codes.intersection(row.get("_reason_codes", "").split("|"))
        ]
        self.quarantine[dataset] = [*retained, *deepcopy(list(rows))]

    def read_bronze(self, dataset: str, batch_id: str, fingerprint: str) -> list[dict[str, str]]:
        return deepcopy(self.bronze[(dataset, batch_id, fingerprint)])

    def read_silver(self, dataset: str) -> list[dict[str, str]]:
        return deepcopy(self.silver.get(dataset, []))

    def read_quarantine(self, dataset: str) -> list[dict[str, str]]:
        return deepcopy(self.quarantine.get(dataset, []))

    def read_quality(self) -> list[dict[str, str]]:
        return deepcopy(self.quality)

    def read_state(self) -> dict[str, Any]:
        return deepcopy(self.state)

    def write_state(self, state: dict[str, Any]) -> None:
        self.state = deepcopy(state)

    def write_reconciliation(self, batch_id: str, value: dict[str, Any]) -> None:
        self.reconciliation[batch_id] = deepcopy(value)

    def write_summary(self, batch_id: str, value: dict[str, Any]) -> None:
        self.summaries[batch_id] = deepcopy(value)

    def read_summary(self, batch_id: str) -> dict[str, Any]:
        return deepcopy(self.summaries[batch_id])


@pytest.mark.contract
def test_pipeline_runs_against_independent_in_memory_storage(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    storage = InMemoryStorage()

    first = process_batch(batch, tmp_path / "unused", storage=storage)
    replay = process_batch(batch, tmp_path / "unused", storage=storage)

    assert isinstance(storage, PipelineStorage)
    assert first.status == "success"
    assert replay.status == "already_processed"
    assert len(storage.read_silver("invoices")) == 720
    assert storage.reconciliation[first.batch_id]["datasets"]["invoices"]["financial_total_matches"]
