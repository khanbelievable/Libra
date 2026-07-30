from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from datalibra.snowflake.loader import load_package
from datalibra.snowflake.package import LoadPackage, PackageItem


class FakeCursor:
    def __init__(self, prior: tuple[str] | None = None, fail_call: bool = False) -> None:
        self.prior = prior
        self.fail_call = fail_call
        self.commands: list[str] = []
        self.called = False

    def execute(self, command: str, params: tuple[Any, ...] | None = None) -> None:
        self.commands.append(command)
        if self.fail_call and command.startswith("CALL "):
            raise RuntimeError("publication failed")
        if command.startswith("CALL "):
            self.called = True

    def fetchone(self) -> tuple[str] | None:
        if self.called:
            return ("SUCCEEDED",)
        return self.prior


def _package(tmp_path: Path) -> LoadPackage:
    source = tmp_path / "invoices.csv"
    source.write_text("invoice_id,amount_eur\nI1,1.00\n", encoding="utf-8")
    return LoadPackage(
        "load-one",
        "1.0",
        "2026-07-30T00:00:00+00:00",
        "a" * 64,
        (PackageItem("invoices", source, 1, "b" * 64, Decimal("1.00")),),
    )


def test_unchanged_successful_fingerprint_is_a_noop(tmp_path: Path) -> None:
    cursor = FakeCursor(("SUCCEEDED",))
    assert load_package(cursor, _package(tmp_path)) == "UNCHANGED"
    assert len(cursor.commands) == 1


def test_load_is_transactional_and_publishes_once(tmp_path: Path) -> None:
    cursor = FakeCursor()
    assert load_package(cursor, _package(tmp_path)) == "LOADED"
    assert cursor.commands.count("BEGIN") == 1
    assert cursor.commands.count("COMMIT") == 1
    assert sum(command.startswith("CALL ") for command in cursor.commands) == 1


def test_load_rolls_back_on_publication_failure(tmp_path: Path) -> None:
    cursor = FakeCursor(fail_call=True)
    with pytest.raises(RuntimeError, match="publication failed"):
        load_package(cursor, _package(tmp_path))
    assert "ROLLBACK" in cursor.commands
    assert cursor.commands[-1].startswith("UPDATE LIBRA.CONTROL.LOAD_RUN")
