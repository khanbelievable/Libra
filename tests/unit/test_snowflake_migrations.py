from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from datalibra.snowflake.migrations import (
    Migration,
    apply_migrations,
    discover_migrations,
    split_statements,
)


class FakeCursor:
    def __init__(self, history: dict[str, str] | None = None) -> None:
        self.history = history or {}
        self.commands: list[tuple[str, tuple[str, ...] | None]] = []
        self.current_version = ""

    def execute(self, command: str, params: tuple[str, ...] | None = None) -> None:
        self.commands.append((command, params))
        if command.startswith("SELECT CHECKSUM"):
            assert params
            self.current_version = params[0]
        elif command.startswith("INSERT INTO LIBRA.CONTROL.MIGRATION_HISTORY"):
            assert params
            self.history[params[0]] = params[2]

    def fetchone(self) -> tuple[Any, ...] | None:
        checksum = self.history.get(self.current_version)
        return (checksum,) if checksum else None


def test_repository_migrations_are_ordered_and_nonempty() -> None:
    migrations = discover_migrations(Path("snowflake/migrations"))
    assert [migration.version for migration in migrations] == ["001", "002", "003", "004"]
    assert all(split_statements(migration.sql) for migration in migrations)


def test_invalid_migration_filename_fails(tmp_path: Path) -> None:
    (tmp_path / "wrong.sql").write_text("SELECT 1", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid migration filename"):
        discover_migrations(tmp_path)


def test_migrations_apply_once_and_detect_checksum_drift() -> None:
    migration = Migration("001", "001_demo", "SELECT 1", hashlib.sha256(b"SELECT 1").hexdigest())
    cursor = FakeCursor()
    assert apply_migrations(cursor, [migration]) == ("001",)
    assert apply_migrations(cursor, [migration]) == ()
    changed = Migration("001", "001_demo", "SELECT 2", hashlib.sha256(b"SELECT 2").hexdigest())
    with pytest.raises(RuntimeError, match="Checksum drift"):
        apply_migrations(cursor, [changed])
