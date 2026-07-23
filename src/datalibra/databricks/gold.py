"""Spark implementation of the five Milestone 1 Gold contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datalibra.databricks.transforms import MONEY_TYPE, PERCENT_TYPE


def _month(column: Any) -> Any:
    from pyspark.sql import functions as F

    return F.trunc(column, "month")


def _ratio(numerator: Any, denominator: Any) -> Any:
    from pyspark.sql import functions as F

    return (
        F.when(denominator != 0, numerator / denominator).otherwise(F.lit(None)).cast(PERCENT_TYPE)
    )


def build_gold_dataframes(silver: Mapping[str, Any], quality: Any) -> dict[str, Any]:
    """Aggregate trusted Spark Silver frames into the five Gold DataFrames."""

    from pyspark.sql import Window
    from pyspark.sql import functions as F

    shipments = silver["shipments"].select(
        "shipment_id",
        "shipment_date",
        "route_id",
        "customer_id",
        "country_code",
        "cost_center_id",
    )
    shipment_lookup = shipments.select(
        "shipment_id",
        F.col("route_id").alias("_shipment_route_id"),
        F.col("customer_id").alias("_shipment_customer_id"),
    )
    invoices = silver["invoices"].join(shipment_lookup, "shipment_id", "inner")
    costs = silver["operational_costs"].join(shipment_lookup, "shipment_id", "inner")
    routes = silver["routes"].select(
        "route_id",
        "origin_country_code",
        "destination_country_code",
        "transport_mode",
    )
    cost_centers = silver["cost_centers"].select("cost_center_id", "country_code")

    rate_window = Window.partitionBy(_month(F.col("rate_date")), "currency_code").orderBy(
        "rate_date"
    )
    month_open_rates = (
        silver["exchange_rates"]
        .withColumn("_rate_rank", F.row_number().over(rate_window))
        .filter(F.col("_rate_rank") == 1)
        .select(
            _month(F.col("rate_date")).alias("_rate_month"),
            F.col("currency_code").alias("_rate_currency"),
            F.col("rate_to_eur").alias("_month_open_rate"),
        )
    )
    invoices = (
        invoices.join(
            month_open_rates,
            (_month(F.col("invoice_date")) == F.col("_rate_month"))
            & (F.col("currency_code") == F.col("_rate_currency")),
            "left",
        )
        .withColumn(
            "_comparison_eur",
            (F.col("revenue_amount") * F.col("_month_open_rate")).cast(MONEY_TYPE),
        )
        .withColumn("_fx_impact", F.col("amount_eur") - F.col("_comparison_eur"))
    )
    costs = (
        costs.join(
            month_open_rates,
            (_month(F.col("posting_date")) == F.col("_rate_month"))
            & (F.col("currency_code") == F.col("_rate_currency")),
            "left",
        )
        .withColumn(
            "_comparison_eur",
            (F.col("amount") * F.col("_month_open_rate")).cast(MONEY_TYPE),
        )
        .withColumn("_fx_impact", F.col("amount_eur") - F.col("_comparison_eur"))
    )

    revenue_monthly = invoices.groupBy(
        _month(F.col("invoice_date")).alias("month_start"), "country_code"
    ).agg(
        F.sum("amount_eur").cast(MONEY_TYPE).alias("total_revenue_eur"),
        F.sum("_fx_impact").cast(MONEY_TYPE).alias("_revenue_fx_impact"),
    )
    cost_monthly = costs.groupBy(
        _month(F.col("posting_date")).alias("month_start"), "country_code"
    ).agg(
        F.sum("amount_eur").cast(MONEY_TYPE).alias("total_operational_cost_eur"),
        F.sum("_fx_impact").cast(MONEY_TYPE).alias("_cost_fx_impact"),
    )
    shipment_monthly = shipments.groupBy(
        _month(F.col("shipment_date")).alias("month_start"), "country_code"
    ).agg(F.countDistinct("shipment_id").alias("shipment_count"))
    budget_monthly = (
        silver["budgets"]
        .join(cost_centers, "cost_center_id", "inner")
        .groupBy("month_start", "country_code")
        .agg(F.sum("amount_eur").cast(MONEY_TYPE).alias("budget_amount_eur"))
    )
    monthly_keys = (
        revenue_monthly.select("month_start", "country_code")
        .unionByName(cost_monthly.select("month_start", "country_code"))
        .unionByName(shipment_monthly.select("month_start", "country_code"))
        .unionByName(budget_monthly.select("month_start", "country_code"))
        .distinct()
    )
    monthly = (
        monthly_keys.join(revenue_monthly, ["month_start", "country_code"], "left")
        .join(cost_monthly, ["month_start", "country_code"], "left")
        .join(shipment_monthly, ["month_start", "country_code"], "left")
        .join(budget_monthly, ["month_start", "country_code"], "left")
        .fillna(
            0,
            subset=[
                "total_revenue_eur",
                "total_operational_cost_eur",
                "shipment_count",
                "budget_amount_eur",
                "_revenue_fx_impact",
                "_cost_fx_impact",
            ],
        )
        .withColumn(
            "gross_profit_eur",
            (F.col("total_revenue_eur") - F.col("total_operational_cost_eur")).cast(MONEY_TYPE),
        )
        .withColumn(
            "gross_margin_pct",
            _ratio(F.col("gross_profit_eur"), F.col("total_revenue_eur")),
        )
        .withColumn(
            "revenue_per_shipment_eur",
            F.when(
                F.col("shipment_count") != 0,
                F.col("total_revenue_eur") / F.col("shipment_count"),
            ).cast(MONEY_TYPE),
        )
        .withColumn(
            "cost_per_shipment_eur",
            F.when(
                F.col("shipment_count") != 0,
                F.col("total_operational_cost_eur") / F.col("shipment_count"),
            ).cast(MONEY_TYPE),
        )
        .withColumn(
            "budget_variance_amount_eur",
            (F.col("budget_amount_eur") - F.col("total_operational_cost_eur")).cast(MONEY_TYPE),
        )
        .withColumn(
            "budget_variance_pct",
            _ratio(F.col("budget_variance_amount_eur"), F.col("budget_amount_eur")),
        )
        .withColumn(
            "fx_impact_eur",
            (F.col("_revenue_fx_impact") - F.col("_cost_fx_impact")).cast(MONEY_TYPE),
        )
        .select(
            "month_start",
            "country_code",
            "total_revenue_eur",
            "total_operational_cost_eur",
            "gross_profit_eur",
            "gross_margin_pct",
            "shipment_count",
            "revenue_per_shipment_eur",
            "cost_per_shipment_eur",
            "budget_amount_eur",
            "budget_variance_amount_eur",
            "budget_variance_pct",
            "fx_impact_eur",
        )
    )

    route_revenue = invoices.groupBy(
        _month(F.col("invoice_date")).alias("month_start"),
        F.col("_shipment_route_id").alias("route_id"),
    ).agg(F.sum("amount_eur").cast(MONEY_TYPE).alias("total_revenue_eur"))
    route_cost = costs.groupBy(
        _month(F.col("posting_date")).alias("month_start"),
        F.col("route_id"),
    ).agg(F.sum("amount_eur").cast(MONEY_TYPE).alias("allocated_operational_cost_eur"))
    route_shipments = shipments.groupBy(
        _month(F.col("shipment_date")).alias("month_start"), "route_id"
    ).agg(F.countDistinct("shipment_id").alias("shipment_count"))
    route_keys = (
        route_revenue.select("month_start", "route_id")
        .unionByName(route_cost.select("month_start", "route_id"))
        .unionByName(route_shipments.select("month_start", "route_id"))
        .distinct()
    )
    route_profitability = (
        route_keys.join(route_revenue, ["month_start", "route_id"], "left")
        .join(route_cost, ["month_start", "route_id"], "left")
        .join(route_shipments, ["month_start", "route_id"], "left")
        .join(routes, "route_id", "inner")
        .fillna(
            0,
            subset=[
                "total_revenue_eur",
                "allocated_operational_cost_eur",
                "shipment_count",
            ],
        )
        .withColumn(
            "gross_profit_eur",
            (F.col("total_revenue_eur") - F.col("allocated_operational_cost_eur")).cast(MONEY_TYPE),
        )
        .withColumn(
            "gross_margin_pct",
            _ratio(F.col("gross_profit_eur"), F.col("total_revenue_eur")),
        )
        .select(
            "month_start",
            "route_id",
            "origin_country_code",
            "destination_country_code",
            "transport_mode",
            "shipment_count",
            "total_revenue_eur",
            "allocated_operational_cost_eur",
            "gross_profit_eur",
            "gross_margin_pct",
        )
    )

    customer_revenue = invoices.groupBy(
        _month(F.col("invoice_date")).alias("month_start"), "customer_id", "country_code"
    ).agg(F.sum("amount_eur").cast(MONEY_TYPE).alias("total_revenue_eur"))
    customer_cost = costs.groupBy(
        _month(F.col("posting_date")).alias("month_start"),
        F.col("_shipment_customer_id").alias("customer_id"),
    ).agg(F.sum("amount_eur").cast(MONEY_TYPE).alias("allocated_operational_cost_eur"))
    customer_shipments = shipments.groupBy(
        _month(F.col("shipment_date")).alias("month_start"),
        "customer_id",
        "country_code",
    ).agg(F.countDistinct("shipment_id").alias("shipment_count"))
    customer_profitability = (
        customer_shipments.join(
            customer_revenue,
            ["month_start", "customer_id", "country_code"],
            "left",
        )
        .join(customer_cost, ["month_start", "customer_id"], "left")
        .fillna(
            0,
            subset=[
                "total_revenue_eur",
                "allocated_operational_cost_eur",
                "shipment_count",
            ],
        )
        .withColumn(
            "gross_profit_eur",
            (F.col("total_revenue_eur") - F.col("allocated_operational_cost_eur")).cast(MONEY_TYPE),
        )
        .withColumn(
            "gross_margin_pct",
            _ratio(F.col("gross_profit_eur"), F.col("total_revenue_eur")),
        )
        .select(
            "month_start",
            "customer_id",
            "country_code",
            "shipment_count",
            "total_revenue_eur",
            "allocated_operational_cost_eur",
            "gross_profit_eur",
            "gross_margin_pct",
        )
    )

    budget = (
        silver["budgets"]
        .join(cost_centers, "cost_center_id", "inner")
        .groupBy("month_start", "cost_center_id", "country_code")
        .agg(F.sum("amount_eur").cast(MONEY_TYPE).alias("budget_amount_eur"))
    )
    actual = costs.groupBy(
        _month(F.col("posting_date")).alias("month_start"), "cost_center_id"
    ).agg(F.sum("amount_eur").cast(MONEY_TYPE).alias("actual_cost_eur"))
    cost_center_countries = cost_centers.withColumnRenamed("country_code", "_cost_center_country")
    budget_vs_actual = (
        budget.join(actual, ["month_start", "cost_center_id"], "full")
        .join(cost_center_countries, "cost_center_id", "left")
        .withColumn(
            "country_code",
            F.coalesce(F.col("country_code"), F.col("_cost_center_country")),
        )
        .fillna(0, subset=["budget_amount_eur", "actual_cost_eur"])
        .withColumn(
            "budget_variance_amount_eur",
            (F.col("budget_amount_eur") - F.col("actual_cost_eur")).cast(MONEY_TYPE),
        )
        .withColumn(
            "budget_variance_pct",
            _ratio(F.col("budget_variance_amount_eur"), F.col("budget_amount_eur")),
        )
        .select(
            "month_start",
            "cost_center_id",
            "country_code",
            "budget_amount_eur",
            "actual_cost_eur",
            "budget_variance_amount_eur",
            "budget_variance_pct",
        )
    )

    data_quality = quality.select(
        "batch_id",
        "affected_dataset",
        "rule_name",
        "validation_status",
        "failure_reason",
        "failed_row_count",
        F.col("affected_financial_amount_eur")
        .cast(MONEY_TYPE)
        .alias("affected_financial_amount_eur"),
    )
    return {
        "gold_monthly_country_finance": monthly,
        "gold_route_profitability": route_profitability,
        "gold_customer_profitability": customer_profitability,
        "gold_budget_vs_actual": budget_vs_actual,
        "gold_data_quality_summary": data_quality,
    }
