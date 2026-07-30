"""Command line entry point for Snowflake deployment and loading."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from datalibra.snowflake.loader import load_package
from datalibra.snowflake.migrations import apply_migrations, discover_migrations
from datalibra.snowflake.package import validate_package


def _connect(connection_name: str) -> Any:
    try:
        import snowflake.connector
    except ImportError as exc:
        raise RuntimeError("Install datalibra[snowflake] to use authenticated commands") from exc
    return snowflake.connector.connect(connection_name=connection_name)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Libra Snowflake serving adapter")
    result.add_argument("--connection", default="default", help="named Snowflake connection")
    subcommands = result.add_subparsers(dest="command", required=True)
    validate = subcommands.add_parser("validate-package")
    validate.add_argument("package", type=Path)
    migrate = subcommands.add_parser("migrate")
    migrate.add_argument("--migrations", type=Path, default=Path("snowflake/migrations"))
    load = subcommands.add_parser("load")
    load.add_argument("package", type=Path)
    subcommands.add_parser("smoke")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "validate-package":
        package = validate_package(args.package)
        print(f"VALID {package.load_id} {len(package.items)} tables")
        return 0
    connection = _connect(args.connection)
    try:
        cursor = connection.cursor()
        if args.command == "migrate":
            applied = apply_migrations(cursor, discover_migrations(args.migrations))
            print("Applied:", ", ".join(applied) if applied else "none")
        elif args.command == "load":
            print(load_package(cursor, validate_package(args.package)))
        else:
            cursor.execute("SELECT CURRENT_VERSION(), CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            version, role, warehouse = cursor.fetchone()
            print(f"Snowflake {version}; role={role}; warehouse={warehouse}")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
