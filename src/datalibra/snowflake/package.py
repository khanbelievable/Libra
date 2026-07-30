"""Deterministic governed extract package validation."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from datalibra.snowflake.contracts import CONTRACT_VERSION, SOURCE_TABLES

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class PackageItem:
    """Validated source artifact metadata."""

    table: str
    path: Path
    row_count: int
    sha256: str
    financial_total: Decimal | None


@dataclass(frozen=True)
class LoadPackage:
    """Validated package safe to present to the loader."""

    load_id: str
    contract_version: str
    load_timestamp: str
    source_fingerprint: str
    items: tuple[PackageItem, ...]


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _csv_stats(path: Path, financial_column: str | None) -> tuple[int, Decimal | None]:
    total = Decimal("0") if financial_column else None
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path.name} has no header")
        count = 0
        for row in reader:
            count += 1
            if financial_column:
                assert total is not None
                total += Decimal(row[financial_column])
    return count, total


def validate_package(path: Path) -> LoadPackage:
    """Validate manifest completeness, checksums, counts, and totals."""

    manifest_path = path / "manifest.json"
    raw: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if raw.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("Unsupported source contract version")
    if raw.get("status") != "EXPORTED":
        raise ValueError("Package status must be EXPORTED")
    load_timestamp = str(raw.get("load_timestamp", ""))
    try:
        datetime.fromisoformat(load_timestamp)
    except ValueError as exc:
        raise ValueError("load_timestamp must be ISO-8601") from exc
    fingerprint = str(raw.get("source_fingerprint", ""))
    if SHA256_PATTERN.fullmatch(fingerprint) is None:
        raise ValueError("source_fingerprint must be a lowercase SHA-256 digest")
    manifest_items = {item["source_table"]: item for item in raw.get("items", [])}
    expected = {table.name for table in SOURCE_TABLES}
    if set(manifest_items) != expected:
        raise ValueError("Manifest source tables do not match the contract")
    validated: list[PackageItem] = []
    for table in SOURCE_TABLES:
        item = manifest_items[table.name]
        csv_path = path / f"{table.name}.csv"
        checksum = _hash(csv_path)
        count, total = _csv_stats(csv_path, table.financial_column)
        expected_total = (
            Decimal(str(item["source_financial_total"])) if table.financial_column else None
        )
        if checksum != item["sha256"] or count != item["source_row_count"]:
            raise ValueError(f"Manifest mismatch for {table.name}")
        if total != expected_total:
            raise ValueError(f"Financial total mismatch for {table.name}")
        validated.append(PackageItem(table.name, csv_path, count, checksum, total))
    return LoadPackage(
        load_id=str(raw["load_id"]),
        contract_version=CONTRACT_VERSION,
        load_timestamp=load_timestamp,
        source_fingerprint=fingerprint,
        items=tuple(validated),
    )
