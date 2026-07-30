from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from datalibra.snowflake.contracts import CONTRACT_VERSION, SOURCE_TABLES
from datalibra.snowflake.package import validate_package


def _write_package(path: Path) -> None:
    items = []
    for table in SOURCE_TABLES:
        csv_path = path / f"{table.name}.csv"
        fields = ["id", *([table.financial_column] if table.financial_column else [])]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerow(
                {
                    "id": "one",
                    **({table.financial_column: "1.25"} if table.financial_column else {}),
                }
            )
        items.append(
            {
                "source_table": table.name,
                "source_row_count": 1,
                "source_financial_total": "1.25" if table.financial_column else None,
                "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            }
        )
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "load_id": "test-load",
                "contract_version": CONTRACT_VERSION,
                "load_timestamp": "2026-07-30T00:00:00+00:00",
                "source_fingerprint": "a" * 64,
                "status": "EXPORTED",
                "items": items,
            }
        ),
        encoding="utf-8",
    )


def test_validate_package_checks_every_contract_table(tmp_path: Path) -> None:
    _write_package(tmp_path)
    package = validate_package(tmp_path)
    assert package.load_id == "test-load"
    assert len(package.items) == len(SOURCE_TABLES)


def test_validate_package_rejects_tampering(tmp_path: Path) -> None:
    _write_package(tmp_path)
    with (tmp_path / "invoices.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered,2.00\n")
    with pytest.raises(ValueError, match="Manifest mismatch"):
        validate_package(tmp_path)
