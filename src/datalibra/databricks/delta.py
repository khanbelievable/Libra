"""Delta Lake publication primitives used by Databricks tasks."""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import reduce
from operator import and_
from typing import Any


def _validate_table_name(table_name: str) -> None:
    if not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*){2}", table_name):
        raise ValueError(f"Expected a three-part Unity Catalog table name, got {table_name!r}")


def replace_batch(
    spark: Any,
    frame: Any,
    table_name: str,
    *,
    batch_id: str,
    business_key: Sequence[str],
    supersedes_batch_id: str | None = None,
) -> None:
    """Transactionally replace one declared ownership contribution."""

    from delta.tables import DeltaTable  # type: ignore[import-not-found]
    from pyspark.sql import functions as F

    _validate_table_name(table_name)
    if not spark.catalog.tableExists(table_name):
        frame.write.format("delta").mode("overwrite").saveAsTable(table_name)
        return
    target = DeltaTable.forName(spark, table_name)
    owner_ids = _replacement_owner_ids(batch_id, supersedes_batch_id)
    owner_condition = F.col("target._batch_id").isin(*owner_ids)
    key_condition = reduce(
        and_,
        (F.col(f"target.{field}") == F.col(f"source.{field}") for field in business_key),
    )
    (
        target.alias("target")
        .merge(frame.alias("source"), owner_condition & key_condition)
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .whenNotMatchedBySourceDelete(condition=owner_condition)
        .execute()
    )


def _replacement_owner_ids(
    batch_id: str,
    supersedes_batch_id: str | None,
) -> tuple[str, ...]:
    if supersedes_batch_id is None:
        return (batch_id,)
    if supersedes_batch_id == batch_id:
        raise ValueError("A batch cannot supersede itself")
    return (batch_id, supersedes_batch_id)


def merge_bronze_evidence(spark: Any, frame: Any, table_name: str) -> None:
    """Idempotently append immutable Bronze evidence."""

    from delta.tables import DeltaTable
    from pyspark.sql import functions as F

    _validate_table_name(table_name)
    if not spark.catalog.tableExists(table_name):
        frame.write.format("delta").mode("append").saveAsTable(table_name)
        return
    target = DeltaTable.forName(spark, table_name)
    keys = ("_batch_id", "_source_fingerprint", "_source_row_number")
    condition = reduce(
        and_,
        (F.col(f"target.{field}") == F.col(f"source.{field}") for field in keys),
    )
    (
        target.alias("target")
        .merge(frame.alias("source"), condition)
        .whenNotMatchedInsertAll()
        .execute()
    )


def upsert_reference(
    spark: Any,
    frame: Any,
    table_name: str,
    *,
    business_key: Sequence[str],
) -> None:
    """Merge a conformed reference dataset at its global natural key."""

    from delta.tables import DeltaTable
    from pyspark.sql import functions as F

    _validate_table_name(table_name)
    if not spark.catalog.tableExists(table_name):
        frame.write.format("delta").mode("overwrite").saveAsTable(table_name)
        return
    target = DeltaTable.forName(spark, table_name)
    condition = reduce(
        and_,
        (F.col(f"target.{field}") == F.col(f"source.{field}") for field in business_key),
    )
    (
        target.alias("target")
        .merge(frame.alias("source"), condition)
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )


def reject_cross_batch_fact_collision(
    spark: Any,
    frame: Any,
    table_name: str,
    *,
    batch_id: str,
    business_key: Sequence[str],
    supersedes_batch_id: str | None = None,
) -> None:
    """Fail before publication if an undeclared batch owns the same financial key."""

    from pyspark.sql import functions as F

    _validate_table_name(table_name)
    if not spark.catalog.tableExists(table_name):
        return
    owner_ids = _replacement_owner_ids(batch_id, supersedes_batch_id)
    incoming_keys = frame.select(*business_key).distinct()
    other_owner_keys = (
        spark.table(table_name)
        .filter(~F.col("_batch_id").isin(*owner_ids))
        .select(*business_key)
        .distinct()
    )
    if incoming_keys.join(other_owner_keys, list(business_key), "inner").limit(1).count():
        raise ValueError(
            "DELTA_CROSS_BATCH_FINANCIAL_COLLISION: another active batch owns a "
            f"{table_name} business key. No Silver fact publication started."
        )


def replace_global(frame: Any, table_name: str) -> None:
    """Atomically replace one deterministic global Gold table."""

    _validate_table_name(table_name)
    frame.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        table_name
    )
