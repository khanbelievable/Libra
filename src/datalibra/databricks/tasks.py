"""Databricks wheel entry points for Bronze, Silver, and Gold tasks."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from datalibra.config import load_project_config
from datalibra.databricks.delta import (
    merge_bronze_evidence,
    reject_cross_batch_fact_collision,
    replace_batch,
    replace_global,
    upsert_reference,
)
from datalibra.databricks.gold import build_gold_dataframes
from datalibra.databricks.schemas import source_schema
from datalibra.databricks.transforms import quality_results, standardize_batch
from datalibra.domain.contracts import (
    DATASET_ORDER,
    FACT_DATASETS,
    SOURCE_FIELDS,
    source_fingerprint,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--landing-path", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--batch-id", required=True)
    return parser.parse_args()


def _manifest(landing_path: str) -> dict[str, Any]:
    path = Path(landing_path) / "manifest.json"
    with path.open(encoding="utf-8") as handle:
        value: dict[str, Any] = json.load(handle)
    return value


def _spark() -> Any:
    from pyspark.sql import SparkSession

    active = SparkSession.getActiveSession()
    return active if active is not None else SparkSession.builder.getOrCreate()


def _table(catalog: str, schema: str, layer: str, dataset: str) -> str:
    return f"{catalog}.{schema}.{layer}_{dataset}"


def _read_source_frames(spark: Any, landing_path: str, manifest: dict[str, Any]) -> dict[str, Any]:
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    batch_id = str(manifest["batch_id"])
    fingerprint = str(manifest["fingerprint"])
    timestamp = str(manifest["generated_at"])
    frames: dict[str, Any] = {}
    for dataset in DATASET_ORDER:
        source = (
            spark.read.option("header", "true")
            .schema(source_schema(dataset))
            .csv(f"{landing_path}/{dataset}.csv")
        )
        deterministic_order = [
            F.coalesce(F.col(field), F.lit("")) for field in SOURCE_FIELDS[dataset]
        ]
        frames[dataset] = (
            source.withColumn(
                "_source_row_number",
                F.row_number().over(Window.orderBy(*deterministic_order)),
            )
            .withColumn("_batch_id", F.lit(batch_id))
            .withColumn("_source_file", F.lit(f"{dataset}.csv"))
            .withColumn("_source_fingerprint", F.lit(fingerprint))
            .withColumn("_ingested_at", F.to_timestamp(F.lit(timestamp)))
        )
    return frames


def _validate_manifest(landing_path: str, batch_id: str) -> dict[str, Any]:
    manifest = _manifest(landing_path)
    if manifest.get("batch_id") != batch_id:
        raise ValueError(
            f"Job batch_id {batch_id!r} does not match manifest {manifest.get('batch_id')!r}"
        )
    paths = [Path(landing_path) / f"{dataset}.csv" for dataset in DATASET_ORDER]
    actual = source_fingerprint(paths)
    if actual != manifest.get("fingerprint"):
        raise ValueError("Landing files do not match the manifest source fingerprint")
    _superseded_batch_id(manifest, batch_id)
    return manifest


def _superseded_batch_id(manifest: dict[str, Any], batch_id: str) -> str | None:
    value = manifest.get("supersedes_batch_id")
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", value):
        raise ValueError("Manifest supersedes_batch_id is invalid")
    if value == batch_id:
        raise ValueError("Manifest supersedes_batch_id must identify another batch")
    return value


def land_bronze() -> None:
    """Land one immutable source version into idempotent Bronze Delta tables."""

    args = _arguments()
    manifest = _validate_manifest(args.landing_path, args.batch_id)
    spark = _spark()
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {args.catalog}.{args.schema}")
    frames = _read_source_frames(spark, args.landing_path, manifest)
    for dataset, frame in frames.items():
        merge_bronze_evidence(
            spark,
            frame,
            _table(args.catalog, args.schema, "bronze", dataset),
        )
    print(
        json.dumps(
            {
                "status": "bronze_landed",
                "batch_id": args.batch_id,
                "fingerprint": manifest["fingerprint"],
                "tables": len(frames),
            },
            sort_keys=True,
        )
    )


def build_silver() -> None:
    """Standardize, validate, convert, and merge one batch into Silver Delta."""

    args = _arguments()
    manifest = _validate_manifest(args.landing_path, args.batch_id)
    spark = _spark()
    from pyspark.sql import functions as F

    fingerprint = str(manifest["fingerprint"])
    bronze = {
        dataset: spark.table(_table(args.catalog, args.schema, "bronze", dataset)).filter(
            (F.col("_batch_id") == F.lit(args.batch_id))
            & (F.col("_source_fingerprint") == F.lit(fingerprint))
        )
        for dataset in DATASET_ORDER
    }
    trusted, quarantine = standardize_batch(bronze)
    keys = load_project_config().dataset_keys
    supersedes_batch_id = _superseded_batch_id(manifest, args.batch_id)
    for dataset in FACT_DATASETS:
        reject_cross_batch_fact_collision(
            spark,
            trusted[dataset],
            _table(args.catalog, args.schema, "silver", dataset),
            batch_id=args.batch_id,
            business_key=keys[dataset],
            supersedes_batch_id=supersedes_batch_id,
        )
    for dataset in DATASET_ORDER:
        if dataset in FACT_DATASETS:
            replace_batch(
                spark,
                trusted[dataset],
                _table(args.catalog, args.schema, "silver", dataset),
                batch_id=args.batch_id,
                business_key=keys[dataset],
                supersedes_batch_id=supersedes_batch_id,
            )
        else:
            upsert_reference(
                spark,
                trusted[dataset],
                _table(args.catalog, args.schema, "silver", dataset),
                business_key=keys[dataset],
            )
        replace_batch(
            spark,
            quarantine[dataset],
            _table(args.catalog, args.schema, "quarantine", dataset),
            batch_id=args.batch_id,
            business_key=keys[dataset],
        )
    quality = quality_results(
        quarantine,
        args.batch_id,
        str(manifest["generated_at"]),
    )
    replace_batch(
        spark,
        quality,
        _table(args.catalog, args.schema, "quality", "results"),
        batch_id=args.batch_id,
        business_key=("affected_dataset", "rule_name"),
    )
    print(
        json.dumps(
            {
                "status": "silver_built",
                "batch_id": args.batch_id,
                "trusted_cost_rows": trusted["operational_costs"].count(),
                "quarantined_cost_rows": quarantine["operational_costs"].count(),
            },
            sort_keys=True,
        )
    )


def build_gold_and_validate() -> None:
    """Publish five Gold Delta tables and fail if controls do not reconcile."""

    from pyspark.sql import functions as F

    args = _arguments()
    _validate_manifest(args.landing_path, args.batch_id)
    spark = _spark()
    silver = {
        dataset: spark.table(_table(args.catalog, args.schema, "silver", dataset))
        for dataset in DATASET_ORDER
    }
    quality = spark.table(_table(args.catalog, args.schema, "quality", "results"))
    gold = build_gold_dataframes(silver, quality)
    for name, frame in gold.items():
        replace_global(frame, f"{args.catalog}.{args.schema}.{name}")

    revenue = silver["invoices"].agg(F.sum("amount_eur")).first()[0]
    cost = silver["operational_costs"].agg(F.sum("amount_eur")).first()[0]
    gold_revenue = gold["gold_monthly_country_finance"].agg(F.sum("total_revenue_eur")).first()[0]
    gold_cost = (
        gold["gold_monthly_country_finance"].agg(F.sum("total_operational_cost_eur")).first()[0]
    )
    controls = [
        ("revenue", revenue, gold_revenue, revenue == gold_revenue),
        ("operational_cost", cost, gold_cost, cost == gold_cost),
    ]
    control_frame = spark.createDataFrame(
        controls,
        "metric string, silver_total decimal(20,2), gold_total decimal(20,2), matches boolean",
    )
    replace_global(
        control_frame,
        f"{args.catalog}.{args.schema}.reconciliation_controls",
    )
    if not all(item[3] for item in controls):
        raise ValueError("Databricks Gold totals do not reconcile to trusted Silver")
    print(
        json.dumps(
            {
                "status": "gold_validated",
                "batch_id": args.batch_id,
                "tables": {name: frame.count() for name, frame in gold.items()},
                "revenue_eur": str(revenue),
                "operational_cost_eur": str(cost),
            },
            sort_keys=True,
        )
    )
