"""Shared result models kept independent of storage and compute engines."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

ValidationStatus = Literal["PASS", "FAIL"]
PipelineStatus = Literal["success", "quality_failed", "already_processed"]


@dataclass(frozen=True)
class QualityResult:
    rule_name: str
    affected_dataset: str
    batch_id: str
    failure_reason: str
    failed_row_count: int
    affected_financial_amount_eur: str
    execution_timestamp: str
    validation_status: ValidationStatus

    def as_row(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class PipelineSummary:
    batch_id: str
    scenario: str
    status: PipelineStatus
    fingerprint: str
    bronze_rows: dict[str, int]
    silver_rows: dict[str, int]
    quarantine_rows: dict[str, int]
    failed_rules: tuple[str, ...]
    trusted_invoice_revenue_eur: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
