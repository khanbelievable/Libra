from __future__ import annotations

import os

import pytest


@pytest.mark.snowflake
def test_named_snowflake_connection_is_usable() -> None:
    connection_name = os.getenv("LIBRA_SNOWFLAKE_CONNECTION")
    if not connection_name:
        pytest.skip("LIBRA_SNOWFLAKE_CONNECTION is not configured")
    connector = pytest.importorskip("snowflake.connector")
    connection = connector.connect(connection_name=connection_name)
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT CURRENT_VERSION(), CURRENT_ROLE(), CURRENT_WAREHOUSE()")
        version, role, warehouse = cursor.fetchone()
        assert version
        assert role
        assert warehouse
    finally:
        connection.close()
