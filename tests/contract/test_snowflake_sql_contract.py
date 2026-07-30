from __future__ import annotations

import re
from pathlib import Path

import sqlglot

from datalibra.snowflake.contracts import (
    DATABASE,
    REQUIRED_REPORTING_VIEWS,
    ROLES,
    SCHEMAS,
)
from datalibra.snowflake.migrations import discover_migrations, split_statements


def _all_sql() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(Path("snowflake").glob("**/*.sql"))
    )


def test_sql_defines_governed_names_and_fixed_scale_finance() -> None:
    sql = _all_sql().upper()
    assert f"CREATE DATABASE IF NOT EXISTS {DATABASE}" in sql
    assert all(f"LIBRA.{schema}" in sql for schema in SCHEMAS)
    assert all(role in sql for role in ROLES)
    assert "FLOAT" not in sql
    assert "NUMBER(20,2)" in sql
    assert "NUMBER(18,6)" in sql


def test_every_reporting_view_is_executable_contract() -> None:
    sql = _all_sql().upper()
    assert all(
        re.search(rf"CREATE OR REPLACE VIEW LIBRA\.REPORTING\.{view}\b", sql)
        for view in REQUIRED_REPORTING_VIEWS
    )


def test_standard_migration_statements_parse_as_snowflake() -> None:
    migrations = discover_migrations(Path("snowflake/migrations"))
    statements = [
        statement for migration in migrations for statement in split_statements(migration.sql)
    ]
    for statement in statements:
        assert sqlglot.parse_one(statement, read="snowflake") is not None


def test_finance_keys_and_least_privilege_are_explicit() -> None:
    sql = _all_sql().upper()
    for key in ("INVOICE_ID", "COST_ID", "SHIPMENT_ID"):
        assert f"PRIMARY KEY ({key})" in sql
    grants = (
        Path("snowflake/migrations/004_security_and_controls.sql")
        .read_text(encoding="utf-8")
        .upper()
    )
    assert "LIBRA_LOADER" in grants
    assert "SCHEMA LIBRA.REPORTING TO ROLE LIBRA_LOADER" not in grants
    assert "LIBRA_FINANCE_READER" in grants
    assert "LIBRA_DQ_READER" in grants
