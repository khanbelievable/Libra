"""Versioned contracts for governed Databricks extracts."""

from __future__ import annotations

from dataclasses import dataclass

CONTRACT_VERSION = "1.0"
DATABASE = "LIBRA"
SCHEMAS = ("CONTROL", "LOAD", "CORE", "REPORTING")
ROLES = ("LIBRA_OWNER", "LIBRA_LOADER", "LIBRA_FINANCE_READER", "LIBRA_DQ_READER")


@dataclass(frozen=True)
class SourceTable:
    """One approved extract and its immutable loading contract."""

    name: str
    natural_key: tuple[str, ...]
    financial_column: str | None = None


SOURCE_TABLES = (
    SourceTable("countries", ("country_code",)),
    SourceTable("currencies", ("currency_code",)),
    SourceTable("customers", ("customer_id",)),
    SourceTable("cost_centers", ("cost_center_id",)),
    SourceTable("routes", ("route_id",)),
    SourceTable("shipments", ("shipment_id",), "amount_eur"),
    SourceTable("invoices", ("invoice_id",), "amount_eur"),
    SourceTable("operational_costs", ("cost_id",), "amount_eur"),
    SourceTable("budgets", ("month_start", "cost_center_id"), "amount_eur"),
    SourceTable("data_quality_results", ("batch_id", "affected_dataset", "rule_name")),
)

SOURCE_TABLE_NAMES = tuple(table.name for table in SOURCE_TABLES)

REQUIRED_REPORTING_VIEWS = (
    "DIM_DATE",
    "DIM_COUNTRY",
    "DIM_CUSTOMER",
    "DIM_ROUTE",
    "DIM_COST_CENTER",
    "DIM_CURRENCY",
    "FACT_SHIPMENT",
    "FACT_INVOICE",
    "FACT_OPERATIONAL_COST",
    "FACT_BUDGET",
    "FACT_DATA_QUALITY_RESULT",
    "MONTHLY_COUNTRY_FINANCE",
    "ROUTE_PROFITABILITY",
    "CUSTOMER_PROFITABILITY",
    "BUDGET_VS_ACTUAL",
    "DATA_QUALITY_SUMMARY",
    "REFRESH_STATUS",
    "RECONCILIATION_STATUS",
    "TRANSACTION_DRILLTHROUGH",
)

ORACLE = {
    "invoice_count": 720,
    "operational_cost_count": 2880,
    "revenue_eur": "916351.47",
    "operational_cost_eur": "230279.65",
    "gross_profit_eur": "686071.82",
    "budget_eur": "3048056.60",
    "monthly_country_finance_count": 60,
    "route_profitability_count": 120,
    "customer_profitability_count": 240,
    "budget_vs_actual_count": 120,
    "healthy_data_quality_count": 38,
    "retained_data_quality_count": 76,
}
