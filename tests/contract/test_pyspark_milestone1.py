from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DateType, DecimalType

from datalibra.databricks.gold import build_gold_dataframes
from datalibra.databricks.tasks import _read_source_frames
from datalibra.databricks.transforms import standardize_batch
from datalibra.generators import generate_scenario
from datalibra.orchestration import run_local_batch


@pytest.fixture(scope="module")
def spark(tmp_path_factory: pytest.TempPathFactory) -> Any:
    warehouse = tmp_path_factory.mktemp("spark-warehouse")
    session = (
        SparkSession.builder.master("local[2]")
        .appName("libra-milestone-1-contracts")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.warehouse.dir", warehouse.resolve().as_uri())
        .config("spark.driver.bindAddress", "127.0.0.1")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def _frames(spark: Any, batch: Path) -> dict[str, Any]:
    manifest = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
    return _read_source_frames(spark, batch.as_posix(), manifest)


@pytest.mark.spark
@pytest.mark.contract
def test_pyspark_silver_uses_decimal_types_and_quarantines_cost_failures(
    spark: Any, tmp_path: Path
) -> None:
    healthy = generate_scenario("healthy", tmp_path / "healthy")
    trusted, quarantine = standardize_batch(_frames(spark, healthy))

    assert trusted["routes"].count() == 10
    assert trusted["shipments"].count() == 720
    assert trusted["operational_costs"].count() == 2880
    assert quarantine["operational_costs"].count() == 0
    cost_schema = trusted["operational_costs"].schema
    assert cost_schema["posting_date"].dataType == DateType()
    assert cost_schema["amount"].dataType == DecimalType(20, 2)
    assert cost_schema["fx_rate_to_eur"].dataType == DecimalType(18, 6)
    assert cost_schema["amount_eur"].dataType == DecimalType(20, 2)

    broken = generate_scenario("invalid_operational_costs", tmp_path / "broken")
    broken_trusted, broken_quarantine = standardize_batch(_frames(spark, broken))
    reasons = {
        row["_reason_codes"]
        for row in broken_quarantine["operational_costs"].select("_reason_codes").collect()
    }
    assert broken_trusted["operational_costs"].count() == 2871
    assert reasons == {
        "INVALID_COST_TYPE",
        "INVALID_FINANCIAL_VALUE",
        "MISSING_EXCHANGE_RATE",
        "UNKNOWN_COST_CENTER_ID",
        "UNKNOWN_COUNTRY_CODE",
        "UNKNOWN_CURRENCY_CODE",
        "UNKNOWN_ROUTE_ID",
        "UNKNOWN_SHIPMENT_ID",
    }


@pytest.mark.spark
@pytest.mark.contract
def test_pyspark_gold_matches_local_financial_oracle(spark: Any, tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    trusted, _ = standardize_batch(_frames(spark, batch))
    quality = spark.createDataFrame(
        [],
        (
            "batch_id string, affected_dataset string, rule_name string, "
            "validation_status string, failure_reason string, failed_row_count long, "
            "affected_financial_amount_eur decimal(20,2)"
        ),
    )

    gold = build_gold_dataframes(trusted, quality)
    _, local_controls = run_local_batch(batch, tmp_path / "local-output")

    monthly = gold["gold_monthly_country_finance"]
    spark_revenue = monthly.agg(F.sum("total_revenue_eur")).first()[0]
    spark_cost = monthly.agg(F.sum("total_operational_cost_eur")).first()[0]
    spark_budget = monthly.agg(F.sum("budget_amount_eur")).first()[0]
    assert str(spark_revenue) == local_controls["trusted_silver_totals_eur"]["revenue"]
    assert str(spark_cost) == local_controls["trusted_silver_totals_eur"]["operational_cost"]
    assert str(spark_budget) == local_controls["trusted_silver_totals_eur"]["budget"]
    assert spark_revenue - spark_cost == Decimal(
        local_controls["trusted_silver_totals_eur"]["gross_profit"]
    )
    assert {name: frame.count() for name, frame in gold.items()} == {
        "gold_budget_vs_actual": 120,
        "gold_customer_profitability": 240,
        "gold_data_quality_summary": 0,
        "gold_monthly_country_finance": 60,
        "gold_route_profitability": 120,
    }
