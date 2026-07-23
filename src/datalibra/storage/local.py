"""Atomic, dependency-free CSV/JSON storage for local demonstrations."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from datalibra.domain.contracts import fingerprint_storage_id


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _ordered_fields(rows: Sequence[dict[str, str]]) -> list[str]:
    if not rows:
        return []
    fields = list(rows[0])
    seen = set(fields)
    for row in rows[1:]:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    return fields


def _spreadsheet_safe(value: str) -> str:
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def write_csv_atomic(
    path: Path,
    rows: Sequence[dict[str, str]],
    fields: Sequence[str] | None = None,
    *,
    protect_spreadsheets: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    target_fields = list(fields or _ordered_fields(rows))
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        if target_fields:
            writer = csv.DictWriter(
                handle, fieldnames=target_fields, extrasaction="ignore", lineterminator="\n"
            )
            writer.writeheader()
            output_rows = (
                [
                    {field: _spreadsheet_safe(str(value)) for field, value in row.items()}
                    for row in rows
                ]
                if protect_spreadsheets
                else rows
            )
            writer.writerows(output_rows)
    temporary.replace(path)


def write_spreadsheet_csv_export(
    path: Path,
    rows: Sequence[dict[str, str]],
    fields: Sequence[str] | None = None,
) -> None:
    """Write a presentation-only CSV with formula-leading cells neutralized."""

    write_csv_atomic(path, rows, fields, protect_spreadsheets=True)


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


class LocalCsvStorage:
    """Persist batch evidence and merge trusted rows by configured business key."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def write_bronze(
        self,
        dataset: str,
        batch_id: str,
        fingerprint: str,
        rows: Sequence[dict[str, str]],
    ) -> None:
        path = self._bronze_path(dataset, batch_id, fingerprint)
        if path.exists() and path.stat().st_size:
            stored_fingerprints = {row.get("_source_fingerprint", "") for row in read_csv(path)}
            if stored_fingerprints != {fingerprint}:
                raise RuntimeError(
                    "Bronze storage identifier collision for "
                    f"{batch_id}/{fingerprint_storage_id(fingerprint)}"
                )
        write_csv_atomic(path, rows)

    def _bronze_path(self, dataset: str, batch_id: str, fingerprint: str) -> Path:
        return (
            self.root / "bronze" / dataset / f"{batch_id}-{fingerprint_storage_id(fingerprint)}.csv"
        )

    def replace_batch_and_merge_silver(
        self,
        dataset: str,
        batch_id: str,
        rows: Sequence[dict[str, str]],
        business_key: tuple[str, ...],
    ) -> None:
        path = self.root / "silver" / f"{dataset}.csv"
        existing = read_csv(path) if path.exists() and path.stat().st_size else []
        retained = [row for row in existing if row.get("_batch_id") != batch_id]
        merged: dict[tuple[str, ...], dict[str, str]] = {
            tuple(row[field] for field in business_key): row for row in retained
        }
        for row in rows:
            merged[tuple(row[field] for field in business_key)] = dict(row)
        ordered = [merged[key] for key in sorted(merged)]
        fields = _ordered_fields([*rows, *existing])
        write_csv_atomic(path, ordered, fields)

    def replace_all_silver(
        self,
        dataset: str,
        rows: Sequence[dict[str, str]],
        business_key: tuple[str, ...],
    ) -> None:
        ordered = sorted(rows, key=lambda row: tuple(row[field] for field in business_key))
        write_csv_atomic(self.root / "silver" / f"{dataset}.csv", ordered)

    def replace_batch_quarantine(
        self, dataset: str, batch_id: str, rows: Sequence[dict[str, str]]
    ) -> None:
        path = self.root / "quarantine" / f"{dataset}.csv"
        existing = read_csv(path) if path.exists() and path.stat().st_size else []
        retained = [row for row in existing if row.get("_batch_id") != batch_id]
        combined = [*retained, *(dict(row) for row in rows)]
        combined.sort(key=lambda row: (row.get("_batch_id", ""), row.get("_source_row_number", "")))
        fields = _ordered_fields([*rows, *existing])
        write_csv_atomic(path, combined, fields)

    def replace_batch_quality(self, batch_id: str, rows: Sequence[dict[str, str]]) -> None:
        path = self.root / "quality" / "quality_results.csv"
        existing = read_csv(path) if path.exists() and path.stat().st_size else []
        retained = [row for row in existing if row.get("batch_id") != batch_id]
        combined = [*retained, *(dict(row) for row in rows)]
        combined.sort(key=lambda row: (row["batch_id"], row["affected_dataset"], row["rule_name"]))
        fields = (
            "rule_name",
            "affected_dataset",
            "batch_id",
            "failure_reason",
            "failed_row_count",
            "affected_financial_amount_eur",
            "execution_timestamp",
            "validation_status",
        )
        write_csv_atomic(path, combined, fields)

    def replace_batch_claim_manifest(
        self, dataset: str, batch_id: str, rows: Sequence[dict[str, str]]
    ) -> None:
        path = self.root / "claims" / dataset / f"{batch_id}.csv"
        ordered = sorted(rows, key=lambda row: row.get("_source_row_number", ""))
        write_csv_atomic(path, ordered)

    def read_batch_claim_manifest(self, dataset: str, batch_id: str) -> list[dict[str, str]]:
        path = self.root / "claims" / dataset / f"{batch_id}.csv"
        return read_csv(path) if path.exists() and path.stat().st_size else []

    def replace_all_claims(self, dataset: str, rows: Sequence[dict[str, str]]) -> None:
        path = self.root / "claims" / f"{dataset}.csv"
        ordered = sorted(
            rows,
            key=lambda row: (
                row.get("_batch_id", ""),
                row.get("_source_row_number", ""),
            ),
        )
        write_csv_atomic(path, ordered, _ordered_fields(ordered))

    def read_claims(self, dataset: str) -> list[dict[str, str]]:
        path = self.root / "claims" / f"{dataset}.csv"
        return read_csv(path) if path.exists() and path.stat().st_size else []

    def replace_dedup_quarantine(
        self,
        dataset: str,
        rows: Sequence[dict[str, str]],
        reason_codes: frozenset[str],
    ) -> None:
        path = self.root / "quarantine" / f"{dataset}.csv"
        existing = read_csv(path) if path.exists() and path.stat().st_size else []
        retained = [
            row
            for row in existing
            if not reason_codes.intersection(row.get("_reason_codes", "").split("|"))
        ]
        combined = [*retained, *(dict(row) for row in rows)]
        combined.sort(
            key=lambda row: (
                row.get("_batch_id", ""),
                row.get("_source_row_number", ""),
            )
        )
        write_csv_atomic(path, combined, _ordered_fields([*rows, *existing]))

    def read_bronze(self, dataset: str, batch_id: str, fingerprint: str) -> list[dict[str, str]]:
        return read_csv(self._bronze_path(dataset, batch_id, fingerprint))

    def read_silver(self, dataset: str) -> list[dict[str, str]]:
        path = self.root / "silver" / f"{dataset}.csv"
        return read_csv(path) if path.exists() and path.stat().st_size else []

    def read_quarantine(self, dataset: str) -> list[dict[str, str]]:
        path = self.root / "quarantine" / f"{dataset}.csv"
        return read_csv(path) if path.exists() and path.stat().st_size else []

    def read_quality(self) -> list[dict[str, str]]:
        path = self.root / "quality" / "quality_results.csv"
        return read_csv(path) if path.exists() and path.stat().st_size else []

    def read_state(self) -> dict[str, Any]:
        path = self.root / "state" / "processed_batches.json"
        if not path.exists():
            return {"batches": {}, "latest_successful_refresh_timestamp": None}
        with path.open(encoding="utf-8") as handle:
            state: dict[str, Any] = json.load(handle)
        return state

    def write_state(self, state: dict[str, Any]) -> None:
        write_json_atomic(self.root / "state" / "processed_batches.json", state)

    def write_reconciliation(self, batch_id: str, value: dict[str, Any]) -> None:
        write_json_atomic(self.root / "reconciliation" / f"{batch_id}.json", value)

    def read_reconciliation(self, batch_id: str) -> dict[str, Any]:
        path = self.root / "reconciliation" / f"{batch_id}.json"
        with path.open(encoding="utf-8") as handle:
            value: dict[str, Any] = json.load(handle)
        return value

    def write_summary(self, batch_id: str, value: dict[str, Any]) -> None:
        write_json_atomic(self.root / "runs" / f"{batch_id}.json", value)

    def read_summary(self, batch_id: str) -> dict[str, Any]:
        path = self.root / "runs" / f"{batch_id}.json"
        with path.open(encoding="utf-8") as handle:
            value: dict[str, Any] = json.load(handle)
        return value


def rows_by_batch(rows: Iterable[dict[str, str]], batch_id: str) -> list[dict[str, str]]:
    return [row for row in rows if row.get("_batch_id") == batch_id]
