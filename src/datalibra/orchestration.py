"""Milestone 1 local orchestration over the trusted Silver core and Gold oracle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from datalibra.domain.models import PipelineSummary
from datalibra.gold import publish_local_gold
from datalibra.silver import process_batch
from datalibra.storage.local import LocalCsvStorage, read_csv, write_json_atomic


def run_local_batch(
    batch_dir: Path, output_root: Path
) -> tuple[PipelineSummary, dict[str, Any]]:
    """Process one batch and rebuild deterministic Gold from committed Silver."""

    summary = process_batch(batch_dir, output_root)
    controls = publish_local_gold(output_root)
    return summary, controls


def _monthly_country_row(output_root: Path, month: str, country: str) -> dict[str, str]:
    return next(
        row
        for row in read_csv(output_root / "gold" / "gold_monthly_country_finance.csv")
        if row["month_start"] == month and row["country_code"] == country
    )


def run_correction_demo(input_root: Path, output_root: Path) -> dict[str, Any]:
    """Run one owner-scoped late cost correction and persist before/after evidence."""

    initial, initial_controls = run_local_batch(
        input_root / "cost_correction_initial", output_root
    )
    before = _monthly_country_row(output_root, "2025-01-01", "DE")
    corrected, corrected_controls = run_local_batch(
        input_root / "cost_correction_corrected", output_root
    )
    after = _monthly_country_row(output_root, "2025-01-01", "DE")
    storage = LocalCsvStorage(output_root)
    costs = storage.read_silver("operational_costs")
    state = storage.read_state()
    cost_ids = [row["cost_id"] for row in costs]
    audit: dict[str, Any] = {
        "batch_id": corrected.batch_id,
        "historical_period": "2025-01-01",
        "country_code": "DE",
        "initial": {
            "fingerprint": initial.fingerprint,
            "operational_cost_rows": initial.silver_rows["operational_costs"],
            "total_operational_cost_eur": before["total_operational_cost_eur"],
            "gross_profit_eur": before["gross_profit_eur"],
            "global_controls": initial_controls["trusted_silver_totals_eur"],
        },
        "corrected": {
            "fingerprint": corrected.fingerprint,
            "operational_cost_rows": corrected.silver_rows["operational_costs"],
            "total_operational_cost_eur": after["total_operational_cost_eur"],
            "gross_profit_eur": after["gross_profit_eur"],
            "global_controls": corrected_controls["trusted_silver_totals_eur"],
        },
        "arrival_sequence": state["batches"][corrected.batch_id]["arrival_sequence"],
        "trusted_cost_id_count": len(cost_ids),
        "trusted_cost_ids_are_unique": len(cost_ids) == len(set(cost_ids)),
        "trusted_invoice_count": len(storage.read_silver("invoices")),
    }
    write_json_atomic(output_root / "correction" / "cost_correction.json", audit)
    return audit
