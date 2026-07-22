from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from datalibra.storage.local import LocalCsvStorage
from tests.helpers import read_rows


class FaultInjectingStorage(LocalCsvStorage):
    """Simulate a storage adapter that acknowledges a corrupt Silver write."""

    def __init__(self, root: Path, fault: str) -> None:
        super().__init__(root)
        self.fault = fault

    def replace_all_silver(
        self,
        dataset: str,
        rows: list[dict[str, str]],
        business_key: tuple[str, ...],
    ) -> None:
        if dataset != "invoices":
            super().replace_all_silver(dataset, rows, business_key)
            return
        corrupted = [dict(row) for row in rows]
        if self.fault == "drop_half":
            corrupted = corrupted[: len(corrupted) // 2]
        elif self.fault == "alter_amount":
            corrupted[0]["amount_eur"] = str(Decimal(corrupted[0]["amount_eur"]) + Decimal("1.00"))
        elif self.fault == "omit_batch":
            current_batch = corrupted[0]["_batch_id"]
            corrupted = [row for row in corrupted if row["_batch_id"] != current_batch]
        else:
            raise AssertionError(f"Unsupported fault: {self.fault}")
        super().replace_all_silver(dataset, corrupted, business_key)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("fault", "expected_failed_rule"),
    [
        ("drop_half", "SOURCE_TARGET_ROW_RECONCILIATION"),
        ("alter_amount", "SOURCE_TARGET_FINANCIAL_RECONCILIATION"),
        ("omit_batch", "SOURCE_TARGET_ROW_RECONCILIATION"),
    ],
)
def test_reconciliation_uses_committed_readback_and_blocks_refresh(
    tmp_path: Path, fault: str, expected_failed_rule: str
) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"

    summary = process_batch(
        batch,
        output,
        storage=FaultInjectingStorage(output, fault),
    )

    quality = [
        row
        for row in read_rows(output / "quality" / "quality_results.csv")
        if row["affected_dataset"] == "invoices" and row["rule_name"].startswith("SOURCE_TARGET_")
    ]
    state = json.loads((output / "state" / "processed_batches.json").read_text())
    assert summary.status == "quality_failed"
    assert expected_failed_rule in summary.failed_rules
    assert any(row["validation_status"] == "FAIL" for row in quality)
    assert state["batches"][summary.batch_id]["status"] == "quality_failed"
    assert state["latest_successful_refresh_timestamp"] is None
