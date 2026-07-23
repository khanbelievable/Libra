"""Deterministic local Gold oracle for Milestone 1."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from datalibra import PIPELINE_VERSION
from datalibra.config import ProjectConfig, load_project_config
from datalibra.domain.normalization import decimal_string, parse_decimal
from datalibra.storage.local import LocalCsvStorage, write_csv_atomic, write_json_atomic

GOLD_FIELDS: dict[str, tuple[str, ...]] = {
    "gold_monthly_country_finance": (
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
    ),
    "gold_route_profitability": (
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
    ),
    "gold_customer_profitability": (
        "month_start",
        "customer_id",
        "country_code",
        "shipment_count",
        "total_revenue_eur",
        "allocated_operational_cost_eur",
        "gross_profit_eur",
        "gross_margin_pct",
    ),
    "gold_budget_vs_actual": (
        "month_start",
        "cost_center_id",
        "country_code",
        "budget_amount_eur",
        "actual_cost_eur",
        "budget_variance_amount_eur",
        "budget_variance_pct",
    ),
    "gold_data_quality_summary": (
        "batch_id",
        "affected_dataset",
        "rule_name",
        "validation_status",
        "failure_reason",
        "failed_row_count",
        "affected_financial_amount_eur",
    ),
}

MONEY_ZERO = Decimal("0")
PERCENT_SCALE = Decimal("0.0001")


def _month(value: str) -> str:
    return value[:7] + "-01"


def _money(value: Decimal, config: ProjectConfig) -> str:
    return decimal_string(value, config.money_scale)


def _percentage(numerator: Decimal, denominator: Decimal) -> str:
    if not denominator:
        return ""
    return decimal_string(numerator / denominator, PERCENT_SCALE)


def _sum(rows: Iterable[dict[str, str]], field: str = "amount_eur") -> Decimal:
    return sum((parse_decimal(row[field]) for row in rows if row.get(field)), start=MONEY_ZERO)


def _month_open_rates(
    rates: Sequence[dict[str, str]],
) -> dict[tuple[str, str], Decimal]:
    selected: dict[tuple[str, str], tuple[str, Decimal]] = {}
    for row in rates:
        if not row.get("rate_to_eur"):
            continue
        key = (_month(row["rate_date"]), row["currency_code"])
        candidate = (row["rate_date"], parse_decimal(row["rate_to_eur"]))
        if key not in selected or candidate[0] < selected[key][0]:
            selected[key] = candidate
    return {key: value for key, (_, value) in selected.items()}


def _transaction_fx_impact(
    row: dict[str, str],
    *,
    source_field: str,
    date_field: str,
    month_open_rates: Mapping[tuple[str, str], Decimal],
    config: ProjectConfig,
) -> Decimal:
    comparison = month_open_rates.get((_month(row[date_field]), row["currency_code"]))
    if comparison is None:
        return MONEY_ZERO
    comparison_eur = parse_decimal(
        decimal_string(parse_decimal(row[source_field]) * comparison, config.money_scale)
    )
    return parse_decimal(row["amount_eur"]) - comparison_eur


def build_gold_outputs(
    silver: Mapping[str, Sequence[dict[str, str]]],
    quality_rows: Sequence[dict[str, str]],
    *,
    config: ProjectConfig | None = None,
) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    """Build the five fixed Gold contracts and reconciliation controls."""

    project_config = config or load_project_config()
    invoices = list(silver["invoices"])
    costs = list(silver["operational_costs"])
    shipments = list(silver["shipments"])
    budgets = list(silver["budgets"])
    routes = {row["route_id"]: row for row in silver["routes"]}
    cost_centers = {row["cost_center_id"]: row for row in silver["cost_centers"]}
    shipment_by_id = {row["shipment_id"]: row for row in shipments}
    month_open_rates = _month_open_rates(silver["exchange_rates"])

    revenue_by_month_country: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    cost_by_month_country: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    budget_by_month_country: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    shipment_ids_by_month_country: dict[tuple[str, str], set[str]] = defaultdict(set)
    fx_impact_by_month_country: dict[tuple[str, str], Decimal] = defaultdict(Decimal)

    revenue_by_route: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    cost_by_route: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    shipment_ids_by_route: dict[tuple[str, str], set[str]] = defaultdict(set)
    revenue_by_customer: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    cost_by_customer: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    shipment_ids_by_customer: dict[tuple[str, str], set[str]] = defaultdict(set)
    budget_by_cost_center: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    cost_by_cost_center: dict[tuple[str, str], Decimal] = defaultdict(Decimal)

    for shipment in shipments:
        month = _month(shipment["shipment_date"])
        shipment_ids_by_month_country[(month, shipment["country_code"])].add(
            shipment["shipment_id"]
        )
        shipment_ids_by_route[(month, shipment["route_id"])].add(shipment["shipment_id"])
        shipment_ids_by_customer[(month, shipment["customer_id"])].add(shipment["shipment_id"])

    for invoice in invoices:
        month = _month(invoice["invoice_date"])
        amount = parse_decimal(invoice["amount_eur"])
        country_key = (month, invoice["country_code"])
        revenue_by_month_country[country_key] += amount
        shipment = shipment_by_id[invoice["shipment_id"]]
        revenue_by_route[(month, shipment["route_id"])] += amount
        revenue_by_customer[(month, invoice["customer_id"])] += amount
        fx_impact_by_month_country[country_key] += _transaction_fx_impact(
            invoice,
            source_field="revenue_amount",
            date_field="invoice_date",
            month_open_rates=month_open_rates,
            config=project_config,
        )

    for cost_row in costs:
        month = _month(cost_row["posting_date"])
        amount = parse_decimal(cost_row["amount_eur"])
        country_key = (month, cost_row["country_code"])
        cost_by_month_country[country_key] += amount
        cost_by_route[(month, cost_row["route_id"])] += amount
        shipment = shipment_by_id[cost_row["shipment_id"]]
        cost_by_customer[(month, shipment["customer_id"])] += amount
        cost_by_cost_center[(month, cost_row["cost_center_id"])] += amount
        fx_impact_by_month_country[country_key] -= _transaction_fx_impact(
            cost_row,
            source_field="amount",
            date_field="posting_date",
            month_open_rates=month_open_rates,
            config=project_config,
        )

    for budget_row in budgets:
        key = (budget_row["month_start"], budget_row["cost_center_id"])
        amount = parse_decimal(budget_row["amount_eur"])
        budget_by_cost_center[key] += amount
        country = cost_centers[budget_row["cost_center_id"]]["country_code"]
        budget_by_month_country[(budget_row["month_start"], country)] += amount

    monthly_keys = sorted(
        set(revenue_by_month_country)
        | set(cost_by_month_country)
        | set(budget_by_month_country)
        | set(shipment_ids_by_month_country)
    )
    monthly: list[dict[str, str]] = []
    for month, country in monthly_keys:
        revenue = revenue_by_month_country[(month, country)]
        cost = cost_by_month_country[(month, country)]
        budget = budget_by_month_country[(month, country)]
        profit = revenue - cost
        variance = budget - cost
        shipment_count = len(shipment_ids_by_month_country[(month, country)])
        monthly.append(
            {
                "month_start": month,
                "country_code": country,
                "total_revenue_eur": _money(revenue, project_config),
                "total_operational_cost_eur": _money(cost, project_config),
                "gross_profit_eur": _money(profit, project_config),
                "gross_margin_pct": _percentage(profit, revenue),
                "shipment_count": str(shipment_count),
                "revenue_per_shipment_eur": (
                    _money(revenue / shipment_count, project_config) if shipment_count else ""
                ),
                "cost_per_shipment_eur": (
                    _money(cost / shipment_count, project_config) if shipment_count else ""
                ),
                "budget_amount_eur": _money(budget, project_config),
                "budget_variance_amount_eur": _money(variance, project_config),
                "budget_variance_pct": _percentage(variance, budget),
                "fx_impact_eur": _money(
                    fx_impact_by_month_country[(month, country)], project_config
                ),
            }
        )

    route_keys = sorted(set(revenue_by_route) | set(cost_by_route) | set(shipment_ids_by_route))
    route_profitability: list[dict[str, str]] = []
    for month, route_id in route_keys:
        revenue = revenue_by_route[(month, route_id)]
        cost = cost_by_route[(month, route_id)]
        profit = revenue - cost
        route = routes[route_id]
        route_profitability.append(
            {
                "month_start": month,
                "route_id": route_id,
                "origin_country_code": route["origin_country_code"],
                "destination_country_code": route["destination_country_code"],
                "transport_mode": route["transport_mode"],
                "shipment_count": str(len(shipment_ids_by_route[(month, route_id)])),
                "total_revenue_eur": _money(revenue, project_config),
                "allocated_operational_cost_eur": _money(cost, project_config),
                "gross_profit_eur": _money(profit, project_config),
                "gross_margin_pct": _percentage(profit, revenue),
            }
        )

    customer_keys = sorted(
        set(revenue_by_customer) | set(cost_by_customer) | set(shipment_ids_by_customer)
    )
    customer_profitability: list[dict[str, str]] = []
    for month, customer_id in customer_keys:
        revenue = revenue_by_customer[(month, customer_id)]
        cost = cost_by_customer[(month, customer_id)]
        profit = revenue - cost
        shipment_ids = shipment_ids_by_customer[(month, customer_id)]
        country = shipment_by_id[next(iter(sorted(shipment_ids)))]["country_code"]
        customer_profitability.append(
            {
                "month_start": month,
                "customer_id": customer_id,
                "country_code": country,
                "shipment_count": str(len(shipment_ids)),
                "total_revenue_eur": _money(revenue, project_config),
                "allocated_operational_cost_eur": _money(cost, project_config),
                "gross_profit_eur": _money(profit, project_config),
                "gross_margin_pct": _percentage(profit, revenue),
            }
        )

    budget_keys = sorted(set(budget_by_cost_center) | set(cost_by_cost_center))
    budget_vs_actual: list[dict[str, str]] = []
    for month, cost_center_id in budget_keys:
        budget = budget_by_cost_center[(month, cost_center_id)]
        actual = cost_by_cost_center[(month, cost_center_id)]
        variance = budget - actual
        budget_vs_actual.append(
            {
                "month_start": month,
                "cost_center_id": cost_center_id,
                "country_code": cost_centers[cost_center_id]["country_code"],
                "budget_amount_eur": _money(budget, project_config),
                "actual_cost_eur": _money(actual, project_config),
                "budget_variance_amount_eur": _money(variance, project_config),
                "budget_variance_pct": _percentage(variance, budget),
            }
        )

    data_quality = [
        {
            "batch_id": row["batch_id"],
            "affected_dataset": row["affected_dataset"],
            "rule_name": row["rule_name"],
            "validation_status": row["validation_status"],
            "failure_reason": row["failure_reason"],
            "failed_row_count": row["failed_row_count"],
            "affected_financial_amount_eur": row["affected_financial_amount_eur"],
        }
        for row in sorted(
            quality_rows,
            key=lambda item: (
                item["batch_id"],
                item["affected_dataset"],
                item["rule_name"],
            ),
        )
    ]

    outputs = {
        "gold_monthly_country_finance": monthly,
        "gold_route_profitability": route_profitability,
        "gold_customer_profitability": customer_profitability,
        "gold_budget_vs_actual": budget_vs_actual,
        "gold_data_quality_summary": data_quality,
    }
    revenue_total = _sum(invoices)
    cost_total = _sum(costs)
    budget_total = _sum(budgets)
    controls: dict[str, Any] = {
        "pipeline_version": PIPELINE_VERSION,
        "gold_row_counts": {name: len(rows) for name, rows in outputs.items()},
        "trusted_silver_totals_eur": {
            "revenue": _money(revenue_total, project_config),
            "operational_cost": _money(cost_total, project_config),
            "budget": _money(budget_total, project_config),
            "gross_profit": _money(revenue_total - cost_total, project_config),
        },
        "reconciliation": {
            "monthly_revenue_matches": _sum(monthly, "total_revenue_eur") == revenue_total,
            "monthly_cost_matches": _sum(monthly, "total_operational_cost_eur") == cost_total,
            "route_revenue_matches": _sum(route_profitability, "total_revenue_eur")
            == revenue_total,
            "route_cost_matches": _sum(route_profitability, "allocated_operational_cost_eur")
            == cost_total,
            "customer_revenue_matches": _sum(customer_profitability, "total_revenue_eur")
            == revenue_total,
            "customer_cost_matches": _sum(customer_profitability, "allocated_operational_cost_eur")
            == cost_total,
            "budget_matches": _sum(budget_vs_actual, "budget_amount_eur") == budget_total,
            "actual_cost_matches": _sum(budget_vs_actual, "actual_cost_eur") == cost_total,
        },
    }
    if not all(controls["reconciliation"].values()):
        raise ValueError("Gold reconciliation failed against committed Silver controls")
    return outputs, controls


def publish_local_gold(
    output_root: Path, *, config: ProjectConfig | None = None
) -> dict[str, Any]:
    """Build and atomically publish all local Gold contracts."""

    storage = LocalCsvStorage(output_root)
    silver = {
        dataset: storage.read_silver(dataset)
        for dataset in (
            "countries",
            "currencies",
            "exchange_rates",
            "customers",
            "cost_centers",
            "routes",
            "shipments",
            "invoices",
            "budgets",
            "operational_costs",
        )
    }
    outputs, controls = build_gold_outputs(
        silver, storage.read_quality(), config=config
    )
    for name, rows in outputs.items():
        write_csv_atomic(output_root / "gold" / f"{name}.csv", rows, GOLD_FIELDS[name])
    write_json_atomic(output_root / "gold" / "reconciliation.json", controls)
    return controls
