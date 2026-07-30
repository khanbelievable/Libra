from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from datalibra.snowflake import export
from datalibra.snowflake.contracts import SOURCE_TABLES
from datalibra.snowflake.package import validate_package


class FakeDatabricks:
    def __init__(self) -> None:
        self.index = 0

    def query(self, statement: str) -> tuple[list[str], list[list[Any]]]:
        table = SOURCE_TABLES[self.index]
        self.index += 1
        assert "workspace" in statement
        if table.financial_column:
            return [table.financial_column], [["1.25"]]
        return ["id"], [["one"]]


def test_export_queries_are_ordered_and_identifier_safe() -> None:
    queries = export.export_queries("workspace", "libra")
    assert tuple(queries) == tuple(table.name for table in SOURCE_TABLES)
    assert "amount_at_comparison_rate_eur" in queries["invoices"]
    with pytest.raises(ValueError, match="simple SQL identifiers"):
        export.export_queries("workspace; DROP DATABASE", "libra")


def test_build_package_writes_a_self_validating_manifest(tmp_path: Path) -> None:
    output = tmp_path / "package"
    manifest = export.build_package(  # type: ignore[arg-type]
        FakeDatabricks(),
        "workspace",
        "libra",
        output,
        "load-one",
        "2026-07-30T00:00:00+00:00",
    )
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    assert raw["load_id"] == "load-one"
    assert raw["status"] == "EXPORTED"
    assert len(raw["items"]) == 10
    assert validate_package(output).load_id == "load-one"


def test_cli_wrapper_submits_and_reads_inline_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        payload = {
            "statement_id": "statement-one",
            "status": {"state": "SUCCEEDED"},
            "manifest": {"schema": {"columns": [{"name": "VALUE"}]}},
            "result": {"data_array": [["ok"]]},
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(export.subprocess, "run", run)
    client = export.DatabricksCli(tmp_path / "databricks.exe", "LIBRA", "warehouse")
    columns, rows = client.query("SELECT 1")
    assert columns == ["VALUE"]
    assert rows == [["ok"]]
    assert "--json" in calls[0]


def test_export_main_reports_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    expected = tmp_path / "manifest.json"
    monkeypatch.setattr(export, "build_package", lambda *_: expected)
    assert (
        export.main(
            [
                "--databricks",
                str(tmp_path / "databricks.exe"),
                "--warehouse-id",
                "warehouse",
                "--catalog",
                "workspace",
                "--output",
                str(tmp_path / "output"),
            ]
        )
        == 0
    )
