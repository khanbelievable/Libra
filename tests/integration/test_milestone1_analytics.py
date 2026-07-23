from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from datalibra.generators import generate_scenario
from datalibra.gold import GOLD_FIELDS
from datalibra.orchestration import run_correction_demo, run_local_batch
from tests.helpers import read_rows


@pytest.mark.integration
def test_healthy_gold_contracts_reconcile_to_trusted_silver(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"

    summary, controls = run_local_batch(batch, output)

    assert summary.status == "success"
    assert summary.silver_rows["routes"] == 10
    assert summary.silver_rows["operational_costs"] == 2880
    assert controls["gold_row_counts"] == {
        "gold_budget_vs_actual": 120,
        "gold_customer_profitability": 240,
        "gold_data_quality_summary": 38,
        "gold_monthly_country_finance": 60,
        "gold_route_profitability": 120,
    }
    assert controls["trusted_silver_totals_eur"] == {
        "budget": "3048056.60",
        "gross_profit": "686071.82",
        "operational_cost": "230279.65",
        "revenue": "916351.47",
    }
    assert all(controls["reconciliation"].values())

    for name, fields in GOLD_FIELDS.items():
        path = output / "gold" / f"{name}.csv"
        assert path.is_file()
        assert tuple(path.read_text(encoding="utf-8").splitlines()[0].split(",")) == fields

    monthly = read_rows(output / "gold" / "gold_monthly_country_finance.csv")
    assert all(re.fullmatch(r"-?\d+\.\d{2}", row["gross_profit_eur"]) for row in monthly)
    assert all(
        not row["gross_margin_pct"] or re.fullmatch(r"-?\d+\.\d{4}", row["gross_margin_pct"])
        for row in monthly
    )


@pytest.mark.integration
def test_invalid_operational_costs_are_quarantined_with_precise_reasons(
    tmp_path: Path,
) -> None:
    batch = generate_scenario("invalid_operational_costs", tmp_path / "input")
    output = tmp_path / "output"

    summary, controls = run_local_batch(batch, output)
    quarantined = read_rows(output / "quarantine" / "operational_costs.csv")

    assert summary.status == "quality_failed"
    assert summary.silver_rows["operational_costs"] == 2871
    assert len(quarantined) == 9
    assert {row["_reason_codes"] for row in quarantined} == {
        "UNKNOWN_ROUTE_ID",
        "UNKNOWN_SHIPMENT_ID",
        "UNKNOWN_COST_CENTER_ID",
        "UNKNOWN_COUNTRY_CODE",
        "UNKNOWN_CURRENCY_CODE",
        "MISSING_EXCHANGE_RATE",
        "INVALID_FINANCIAL_VALUE",
        "INVALID_COST_TYPE",
    }
    assert all(controls["reconciliation"].values())


@pytest.mark.integration
def test_cost_correction_changes_history_without_duplicates(tmp_path: Path) -> None:
    generated = tmp_path / "input"
    generate_scenario("cost_correction_initial", generated)
    generate_scenario("cost_correction_corrected", generated)

    audit = run_correction_demo(generated, tmp_path / "output")

    assert audit["arrival_sequence"] == 1
    assert audit["initial"]["operational_cost_rows"] == 2879
    assert audit["corrected"]["operational_cost_rows"] == 2880
    assert Decimal(audit["corrected"]["total_operational_cost_eur"]) > Decimal(
        audit["initial"]["total_operational_cost_eur"]
    )
    assert Decimal(audit["corrected"]["gross_profit_eur"]) < Decimal(
        audit["initial"]["gross_profit_eur"]
    )
    assert audit["trusted_cost_ids_are_unique"]
    assert audit["trusted_cost_id_count"] == 2880
    assert audit["trusted_invoice_count"] == 720
    persisted = json.loads(
        (tmp_path / "output" / "correction" / "cost_correction.json").read_text(encoding="utf-8")
    )
    assert persisted == audit
