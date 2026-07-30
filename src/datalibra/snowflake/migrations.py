"""Ordered, checksum-protected Snowflake migrations."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

MIGRATION_PATTERN = re.compile(r"^(?P<version>\d{3})_[a-z0-9_]+\.sql$")


class Cursor(Protocol):
    """Minimum connector cursor surface used by the migration runner."""

    def execute(self, command: str, params: tuple[str, ...] | None = None) -> Any: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...


@dataclass(frozen=True)
class Migration:
    """One immutable migration."""

    version: str
    name: str
    sql: str
    checksum: str


def discover_migrations(path: Path) -> tuple[Migration, ...]:
    """Discover strictly ordered migration files."""

    migrations: list[Migration] = []
    for file_path in sorted(path.glob("*.sql")):
        match = MIGRATION_PATTERN.fullmatch(file_path.name)
        if match is None:
            raise ValueError(f"Invalid migration filename: {file_path.name}")
        sql = file_path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=match.group("version"),
                name=file_path.stem,
                sql=sql,
                checksum=hashlib.sha256(sql.encode()).hexdigest(),
            )
        )
    versions = [migration.version for migration in migrations]
    if versions != sorted(set(versions)):
        raise ValueError("Migration versions must be unique and ascending")
    return tuple(migrations)


def split_statements(sql: str) -> tuple[str, ...]:
    """Split migration SQL at explicit statement boundary comments."""

    return tuple(statement.strip() for statement in sql.split("-- statement") if statement.strip())


def apply_migrations(cursor: Cursor, migrations: Iterable[Migration]) -> tuple[str, ...]:
    """Apply new migrations and reject checksum drift."""

    applied: list[str] = []
    for migration in migrations:
        cursor.execute(
            "SELECT CHECKSUM FROM LIBRA.CONTROL.MIGRATION_HISTORY WHERE VERSION = %s",
            (migration.version,),
        )
        row = cursor.fetchone()
        if row is not None:
            if row[0] != migration.checksum:
                raise RuntimeError(f"Checksum drift for migration {migration.version}")
            continue
        for statement in split_statements(migration.sql):
            cursor.execute(statement)
        cursor.execute(
            "INSERT INTO LIBRA.CONTROL.MIGRATION_HISTORY "
            "(VERSION, NAME, CHECKSUM) VALUES (%s, %s, %s)",
            (migration.version, migration.name, migration.checksum),
        )
        applied.append(migration.version)
    return tuple(applied)
