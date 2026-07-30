"""Single-writer, manifest-owned Snowflake package loader."""

from __future__ import annotations

from typing import Any, Protocol

from datalibra.snowflake.package import LoadPackage


class Cursor(Protocol):
    def execute(self, command: str, params: tuple[Any, ...] | None = None) -> Any: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...


def load_package(cursor: Cursor, package: LoadPackage) -> str:
    """Load once by fingerprint; COPY is scoped to this immutable package."""

    cursor.execute(
        "SELECT STATUS FROM LIBRA.CONTROL.LOAD_RUN WHERE SOURCE_FINGERPRINT = %s",
        (package.source_fingerprint,),
    )
    prior = cursor.fetchone()
    if prior is not None and prior[0] == "SUCCEEDED":
        return "UNCHANGED"
    cursor.execute(
        "MERGE INTO LIBRA.CONTROL.LOAD_RUN T USING "
        "(SELECT %s LOAD_ID, %s CONTRACT_VERSION, %s SOURCE_FINGERPRINT) S "
        "ON T.SOURCE_FINGERPRINT=S.SOURCE_FINGERPRINT "
        "WHEN MATCHED THEN UPDATE SET STATUS='RUNNING', STARTED_AT=CURRENT_TIMESTAMP(), "
        "COMPLETED_AT=NULL, ERROR_MESSAGE=NULL "
        "WHEN NOT MATCHED THEN INSERT "
        "(LOAD_ID,CONTRACT_VERSION,SOURCE_FINGERPRINT,STATUS) "
        "VALUES(S.LOAD_ID,S.CONTRACT_VERSION,S.SOURCE_FINGERPRINT,'RUNNING')",
        (package.load_id, package.contract_version, package.source_fingerprint),
    )
    cursor.execute("BEGIN")
    try:
        for item in package.items:
            stage_name = item.table.upper()
            cursor.execute(f"TRUNCATE TABLE LIBRA.LOAD.STG_{stage_name}")
            uri = item.path.resolve().as_uri()
            cursor.execute(
                f"PUT '{uri}' @LIBRA.LOAD.PACKAGE_STAGE/{package.load_id}/ "
                "AUTO_COMPRESS=FALSE OVERWRITE=FALSE"
            )
            cursor.execute(
                f"COPY INTO LIBRA.LOAD.STG_{stage_name} "
                f"FROM @LIBRA.LOAD.PACKAGE_STAGE/{package.load_id}/{item.path.name} "
                "FILE_FORMAT=(FORMAT_NAME=LIBRA.LOAD.GOVERNED_CSV) "
                "MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE ON_ERROR=ABORT_STATEMENT FORCE=TRUE"
            )
            cursor.execute(
                "MERGE INTO LIBRA.CONTROL.LOAD_ITEM T USING "
                "(SELECT %s LOAD_ID,%s SOURCE_TABLE,%s SOURCE_ROW_COUNT,"
                "%s SOURCE_FINANCIAL_TOTAL,%s SHA256) S "
                "ON T.LOAD_ID=S.LOAD_ID AND T.SOURCE_TABLE=S.SOURCE_TABLE "
                "WHEN MATCHED THEN UPDATE SET SOURCE_ROW_COUNT=S.SOURCE_ROW_COUNT,"
                "SOURCE_FINANCIAL_TOTAL=S.SOURCE_FINANCIAL_TOTAL,SHA256=S.SHA256,"
                "STATUS='STAGED',LOADED_AT=CURRENT_TIMESTAMP() "
                "WHEN NOT MATCHED THEN INSERT "
                "(LOAD_ID,SOURCE_TABLE,SOURCE_ROW_COUNT,SOURCE_FINANCIAL_TOTAL,SHA256,STATUS) "
                "VALUES(S.LOAD_ID,S.SOURCE_TABLE,S.SOURCE_ROW_COUNT,"
                "S.SOURCE_FINANCIAL_TOTAL,S.SHA256,'STAGED')",
                (
                    package.load_id,
                    item.table,
                    item.row_count,
                    item.financial_total,
                    item.sha256,
                ),
            )
        cursor.execute("CALL LIBRA.CONTROL.PUBLISH_STAGED_PACKAGE(%s)", (package.load_id,))
        publication = cursor.fetchone()
        if publication is None or publication[0] != "SUCCEEDED":
            raise RuntimeError("Snowflake publication reconciliation failed")
        cursor.execute("COMMIT")
    except Exception:
        cursor.execute("ROLLBACK")
        cursor.execute(
            "UPDATE LIBRA.CONTROL.LOAD_RUN SET STATUS='FAILED',"
            "COMPLETED_AT=CURRENT_TIMESTAMP(),"
            "ERROR_MESSAGE='Publication failed; inspect query history' "
            "WHERE SOURCE_FINGERPRINT=%s",
            (package.source_fingerprint,),
        )
        raise
    return "LOADED"
