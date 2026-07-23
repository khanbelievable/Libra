"""Explicit source and persisted schemas for the Spark execution path."""

from __future__ import annotations

from datalibra.domain.contracts import SOURCE_FIELDS


def source_schema(dataset: str):  # type: ignore[no-untyped-def]
    """Return an all-string source schema; domain casts are explicit transforms."""

    from pyspark.sql.types import StringType, StructField, StructType

    return StructType([StructField(field, StringType(), True) for field in SOURCE_FIELDS[dataset]])


def bronze_schema(dataset: str):  # type: ignore[no-untyped-def]
    """Return source fields plus immutable Bronze provenance."""

    from pyspark.sql.types import IntegerType, StringType, StructField, StructType, TimestampType

    fields = list(source_schema(dataset).fields)
    fields.extend(
        [
            StructField("_batch_id", StringType(), False),
            StructField("_source_file", StringType(), False),
            StructField("_source_row_number", IntegerType(), False),
            StructField("_source_fingerprint", StringType(), False),
            StructField("_ingested_at", TimestampType(), False),
        ]
    )
    return StructType(fields)
