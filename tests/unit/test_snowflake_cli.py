from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from datalibra.snowflake import cli


class FakeCursor:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def execute(self, command: str, params: tuple[Any, ...] | None = None) -> None:
        self.commands.append(command)

    def fetchone(self) -> tuple[Any, ...] | None:
        if self.commands[-1].startswith("SELECT CURRENT_VERSION"):
            return ("9.0", "LIBRA_OWNER", "COMPUTE_WH")
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_value = FakeCursor()
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_value

    def close(self) -> None:
        self.closed = True


def test_validate_package_command_avoids_connection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = type("Package", (), {"load_id": "load-one", "items": (1, 2)})()
    monkeypatch.setattr(cli, "validate_package", lambda _: package)
    assert cli.main(["validate-package", str(tmp_path)]) == 0


def test_smoke_uses_named_connection_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(cli, "_connect", lambda _: connection)
    assert cli.main(["--connection", "libra", "smoke"]) == 0
    assert connection.closed


def test_migrate_and_load_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(cli, "_connect", lambda _: connection)
    monkeypatch.setattr(cli, "discover_migrations", lambda _: ())
    monkeypatch.setattr(cli, "apply_migrations", lambda *_: ("001",))
    assert cli.main(["migrate", "--migrations", str(tmp_path)]) == 0

    package = object()
    monkeypatch.setattr(cli, "validate_package", lambda _: package)
    monkeypatch.setattr(cli, "load_package", lambda *_: "UNCHANGED")
    assert cli.main(["load", str(tmp_path)]) == 0
