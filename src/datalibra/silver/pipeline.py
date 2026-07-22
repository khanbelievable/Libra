"""Dependency-light Bronze-to-Silver reference implementation."""

from __future__ import annotations

import csv
import json
import logging
import re
from collections import Counter
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from datalibra.config import ProjectConfig, load_project_config
from datalibra.domain.contracts import (
    DATE_FIELD,
    FACT_DATASETS,
    IDENTIFIER_FIELDS,
    MONETARY_FIELD,
    SOURCE_FIELDS,
    source_fingerprint,
)
from datalibra.domain.models import PipelineStatus, PipelineSummary, QualityResult
from datalibra.domain.normalization import (
    decimal_string,
    normalize_code,
    normalize_country,
    normalize_date,
    normalize_identifier,
    parse_decimal,
)
from datalibra.quality.rules import REASON_TO_RULE, RULE_DATASETS
from datalibra.storage.base import PipelineStorage
from datalibra.storage.local import LocalCsvStorage

LOGGER = logging.getLogger(__name__)


def _load_manifest(batch_dir: Path) -> dict[str, Any]:
    path = batch_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing batch manifest: {path}")
    with path.open(encoding="utf-8") as handle:
        manifest: dict[str, Any] = json.load(handle)
    batch_id = str(manifest.get("batch_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9._-]+", batch_id):
        raise ValueError(
            "Manifest batch_id must contain only letters, numbers, dot, underscore, hyphen"
        )
    return manifest


def _validate_contract(dataset: str, path: Path, expected_rows: int) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        actual_fields = tuple(reader.fieldnames or ())
        if actual_fields != SOURCE_FIELDS[dataset]:
            raise ValueError(
                "Schema mismatch for "
                f"{dataset}: expected {SOURCE_FIELDS[dataset]}, got {actual_fields}"
            )
        rows = [dict(row) for row in reader]
    if len(rows) != expected_rows:
        raise ValueError(
            f"Manifest count mismatch for {dataset}: expected {expected_rows}, got {len(rows)}"
        )
    return rows


def _provenance(
    row: dict[str, str],
    batch_id: str,
    dataset: str,
    number: int,
    timestamp: str,
    fingerprint: str,
) -> dict[str, str]:
    return {
        **row,
        "_batch_id": batch_id,
        "_source_file": f"{dataset}.csv",
        "_source_row_number": f"{number:08d}",
        "_ingested_at": timestamp,
        "_source_fingerprint": fingerprint,
    }


def _standardize_dimension(dataset: str, row: dict[str, str]) -> dict[str, str]:
    result = dict(row)
    if "country_code" in result:
        result["country_code"] = normalize_country(result["country_code"])
    if "currency_code" in result:
        result["currency_code"] = normalize_code(result["currency_code"])
    if "default_currency" in result:
        result["default_currency"] = normalize_code(result["default_currency"])
    for identifier in ("customer_id", "cost_center_id"):
        if identifier in result:
            result[identifier] = normalize_identifier(result[identifier])
    if dataset == "exchange_rates":
        result["rate_date"] = normalize_date(result["rate_date"])
        result["rate_to_eur"] = decimal_string(
            parse_decimal(result["rate_to_eur"]), Decimal("0.000001")
        )
    return result


def _standardize_fact(dataset: str, row: dict[str, str], config: ProjectConfig) -> dict[str, str]:
    result = dict(row)
    if "country_code" in result:
        result["country_code"] = normalize_country(result["country_code"])
    result["currency_code"] = normalize_code(result["currency_code"])
    result[DATE_FIELD[dataset]] = normalize_date(result[DATE_FIELD[dataset]])
    for identifier in IDENTIFIER_FIELDS[dataset]:
        result[identifier] = normalize_identifier(result.get(identifier, ""))
    money_field = MONETARY_FIELD[dataset]
    result[money_field] = decimal_string(parse_decimal(result[money_field]), config.money_scale)
    return result


def _sum_eur(rows: Sequence[dict[str, str]]) -> Decimal:
    return sum(
        (parse_decimal(row["amount_eur"]) for row in rows if row.get("amount_eur")),
        start=Decimal("0"),
    )


def _quality_result(
    *,
    rule: str,
    dataset: str,
    batch_id: str,
    timestamp: str,
    flagged: Sequence[dict[str, str]],
    reasons: Sequence[str],
    config: ProjectConfig,
) -> QualityResult:
    amount = _sum_eur(flagged)
    return QualityResult(
        rule_name=rule,
        affected_dataset=dataset,
        batch_id=batch_id,
        failure_reason="|".join(sorted(set(reasons))) if flagged else "",
        failed_row_count=len(flagged),
        affected_financial_amount_eur=(
            decimal_string(amount, config.money_scale) if flagged and amount else ""
        ),
        execution_timestamp=timestamp,
        validation_status="FAIL" if flagged else "PASS",
    )


def _previous_summary(storage: PipelineStorage, batch_id: str) -> PipelineSummary:
    value = storage.read_summary(batch_id)
    return PipelineSummary(
        batch_id=str(value["batch_id"]),
        scenario=str(value["scenario"]),
        status="already_processed",
        fingerprint=str(value["fingerprint"]),
        bronze_rows={str(key): int(count) for key, count in value["bronze_rows"].items()},
        silver_rows={str(key): int(count) for key, count in value["silver_rows"].items()},
        quarantine_rows={str(key): int(count) for key, count in value["quarantine_rows"].items()},
        failed_rules=tuple(str(item) for item in value["failed_rules"]),
        trusted_invoice_revenue_eur=str(value["trusted_invoice_revenue_eur"]),
    )


def process_batch(
    batch_dir: Path,
    output_root: Path,
    *,
    config: ProjectConfig | None = None,
    storage: PipelineStorage | None = None,
) -> PipelineSummary:
    """Process one deterministic source batch into local Bronze/Silver evidence."""

    project_config = config or load_project_config()
    manifest = _load_manifest(batch_dir)
    batch_id = str(manifest["batch_id"])
    scenario = str(manifest["scenario"])
    timestamp = str(manifest["generated_at"])
    source_paths = [batch_dir / f"{dataset}.csv" for dataset in project_config.ordered_datasets]
    fingerprint = source_fingerprint(source_paths)
    if fingerprint != manifest.get("fingerprint"):
        raise ValueError(
            "Source fingerprint does not match manifest; regenerate or correct the manifest"
        )

    storage_adapter = storage or LocalCsvStorage(output_root)
    state = storage_adapter.read_state()
    prior = state.get("batches", {}).get(batch_id)
    if prior and prior.get("fingerprint") == fingerprint:
        LOGGER.info(
            "Batch already processed; returning no-op",
            extra={"batch_id": batch_id, "scenario": scenario, "status": "already_processed"},
        )
        return _previous_summary(storage_adapter, batch_id)

    raw: dict[str, list[dict[str, str]]] = {}
    bronze: dict[str, list[dict[str, str]]] = {}
    for dataset in project_config.ordered_datasets:
        rows = _validate_contract(
            dataset, batch_dir / f"{dataset}.csv", int(manifest["datasets"][dataset])
        )
        raw[dataset] = rows
        bronze[dataset] = [
            _provenance(row, batch_id, dataset, number, timestamp, fingerprint)
            for number, row in enumerate(rows, start=1)
        ]
        storage_adapter.write_bronze(dataset, batch_id, fingerprint, bronze[dataset])

    standardized: dict[str, list[dict[str, str]]] = {}
    for dataset in project_config.ordered_datasets:
        if dataset in FACT_DATASETS:
            standardized[dataset] = [
                {
                    **_standardize_fact(dataset, row, project_config),
                    "_batch_id": batch_id,
                    "_source_row_number": f"{number:08d}",
                }
                for number, row in enumerate(raw[dataset], start=1)
            ]
        else:
            standardized[dataset] = [
                {
                    **_standardize_dimension(dataset, row),
                    "_batch_id": batch_id,
                    "_source_row_number": f"{number:08d}",
                }
                for number, row in enumerate(raw[dataset], start=1)
            ]

    customer_ids = {row["customer_id"] for row in standardized["customers"]}
    cost_center_ids = {row["cost_center_id"] for row in standardized["cost_centers"]}
    shipment_ids = {row["shipment_id"] for row in standardized["shipments"]}
    rates = {
        (row["rate_date"], row["currency_code"]): parse_decimal(row["rate_to_eur"])
        for row in standardized["exchange_rates"]
    }
    invoice_counts = Counter(row["country_code"] for row in standardized["invoices"])
    expected_country_codes = {row["country_code"] for row in standardized["countries"]}
    minimum = int(
        Decimal(project_config.expected_invoice_rows_per_country)
        * project_config.country_volume_minimum_ratio
    )
    dropped_countries = {
        country for country in expected_country_codes if invoice_counts.get(country, 0) < minimum
    }

    reasons_by_dataset: dict[str, list[list[str]]] = {
        dataset: [[] for _ in standardized[dataset]] for dataset in FACT_DATASETS
    }
    seen_invoice_ids: set[str] = set()
    for dataset in FACT_DATASETS:
        for index, row in enumerate(standardized[dataset]):
            reasons = reasons_by_dataset[dataset][index]
            if dataset in ("shipments", "invoices") and not row.get("customer_id"):
                reasons.append("MISSING_CUSTOMER_ID")
            if not row.get("cost_center_id"):
                reasons.append("MISSING_COST_CENTER_ID")
            if row.get("customer_id") and row["customer_id"] not in customer_ids:
                reasons.append("UNKNOWN_CUSTOMER_ID")
            if row.get("cost_center_id") and row["cost_center_id"] not in cost_center_ids:
                reasons.append("UNKNOWN_COST_CENTER_ID")
            if dataset == "invoices":
                if row["invoice_id"] in seen_invoice_ids:
                    reasons.append("DUPLICATE_INVOICE")
                else:
                    seen_invoice_ids.add(row["invoice_id"])
                if row["shipment_id"] not in shipment_ids:
                    reasons.append("UNKNOWN_SHIPMENT_ID")
                if row["country_code"] in dropped_countries:
                    reasons.append("COUNTRY_VOLUME_DROP")
            rate = rates.get((row[DATE_FIELD[dataset]], row["currency_code"]))
            if rate is None:
                reasons.append("MISSING_EXCHANGE_RATE")
                row["fx_rate_to_eur"] = ""
                row["amount_eur"] = ""
            else:
                row["fx_rate_to_eur"] = decimal_string(rate, project_config.rate_scale)
                row["amount_eur"] = decimal_string(
                    parse_decimal(row[MONETARY_FIELD[dataset]]) * rate,
                    project_config.money_scale,
                )

    valid: dict[str, list[dict[str, str]]] = {
        dataset: list(rows)
        for dataset, rows in standardized.items()
        if dataset not in FACT_DATASETS
    }
    quarantine: dict[str, list[dict[str, str]]] = {dataset: [] for dataset in FACT_DATASETS}
    for dataset in FACT_DATASETS:
        valid[dataset] = []
        for row, reasons in zip(standardized[dataset], reasons_by_dataset[dataset], strict=True):
            if reasons:
                quarantine[dataset].append({**row, "_reason_codes": "|".join(sorted(set(reasons)))})
            else:
                valid[dataset].append(row)

    quality_results: list[QualityResult] = []
    for rule, datasets in RULE_DATASETS.items():
        applicable_reasons = {
            reason for reason, mapped_rule in REASON_TO_RULE.items() if mapped_rule == rule
        }
        for dataset in datasets:
            flagged = [
                row
                for row in quarantine[dataset]
                if applicable_reasons.intersection(row["_reason_codes"].split("|"))
            ]
            present_reasons = [
                reason
                for row in flagged
                for reason in row["_reason_codes"].split("|")
                if reason in applicable_reasons
            ]
            if rule == "INVOICE_COUNTRY_VOLUME" and dropped_countries:
                quality_results.append(
                    QualityResult(
                        rule_name=rule,
                        affected_dataset=dataset,
                        batch_id=batch_id,
                        failure_reason="COUNTRY_VOLUME_DROP",
                        failed_row_count=len(flagged),
                        affected_financial_amount_eur=(
                            decimal_string(_sum_eur(flagged), project_config.money_scale)
                            if flagged
                            else ""
                        ),
                        execution_timestamp=timestamp,
                        validation_status="FAIL",
                    )
                )
                continue
            quality_results.append(
                _quality_result(
                    rule=rule,
                    dataset=dataset,
                    batch_id=batch_id,
                    timestamp=timestamp,
                    flagged=flagged,
                    reasons=present_reasons,
                    config=project_config,
                )
            )

    reconciliation: dict[str, Any] = {"batch_id": batch_id, "datasets": {}}
    for dataset in project_config.ordered_datasets:
        source_count = len(standardized[dataset])
        trusted_count = len(valid[dataset])
        quarantined_count = len(quarantine.get(dataset, []))
        count_match = source_count == trusted_count + quarantined_count
        reconciliation["datasets"][dataset] = {
            "source_rows": source_count,
            "trusted_rows": trusted_count,
            "quarantined_rows": quarantined_count,
            "row_count_matches": count_match,
        }
        quality_results.append(
            QualityResult(
                rule_name="SOURCE_TARGET_ROW_RECONCILIATION",
                affected_dataset=dataset,
                batch_id=batch_id,
                failure_reason="" if count_match else "ROW_COUNT_MISMATCH",
                failed_row_count=0
                if count_match
                else abs(source_count - trusted_count - quarantined_count),
                affected_financial_amount_eur="",
                execution_timestamp=timestamp,
                validation_status="PASS" if count_match else "FAIL",
            )
        )
        if dataset in FACT_DATASETS:
            source_convertible = _sum_eur(standardized[dataset])
            accounted = _sum_eur(valid[dataset]) + _sum_eur(quarantine[dataset])
            financial_match = source_convertible == accounted
            reconciliation["datasets"][dataset].update(
                {
                    "convertible_source_eur": decimal_string(
                        source_convertible, project_config.money_scale
                    ),
                    "trusted_eur": decimal_string(
                        _sum_eur(valid[dataset]), project_config.money_scale
                    ),
                    "quarantined_convertible_eur": decimal_string(
                        _sum_eur(quarantine[dataset]), project_config.money_scale
                    ),
                    "financial_total_matches": financial_match,
                }
            )
            quality_results.append(
                QualityResult(
                    rule_name="SOURCE_TARGET_FINANCIAL_RECONCILIATION",
                    affected_dataset=dataset,
                    batch_id=batch_id,
                    failure_reason="" if financial_match else "FINANCIAL_TOTAL_MISMATCH",
                    failed_row_count=0 if financial_match else 1,
                    affected_financial_amount_eur=(
                        ""
                        if financial_match
                        else decimal_string(
                            abs(source_convertible - accounted), project_config.money_scale
                        )
                    ),
                    execution_timestamp=timestamp,
                    validation_status="PASS" if financial_match else "FAIL",
                )
            )

    for dataset in project_config.ordered_datasets:
        storage_adapter.replace_batch_and_merge_silver(
            dataset,
            batch_id,
            valid[dataset],
            project_config.dataset_keys[dataset],
        )
        if dataset in FACT_DATASETS:
            storage_adapter.replace_batch_quarantine(dataset, batch_id, quarantine[dataset])
    storage_adapter.replace_batch_quality(batch_id, [result.as_row() for result in quality_results])
    storage_adapter.write_reconciliation(batch_id, reconciliation)

    failed_rules = tuple(
        sorted(
            {
                result.rule_name
                for result in quality_results
                if result.validation_status == "FAIL"
                and result.rule_name in project_config.critical_rules
            }
        )
    )
    status: PipelineStatus = "quality_failed" if failed_rules else "success"
    invoice_revenue = _sum_eur(valid["invoices"])
    summary = PipelineSummary(
        batch_id=batch_id,
        scenario=scenario,
        status=status,
        fingerprint=fingerprint,
        bronze_rows={dataset: len(rows) for dataset, rows in bronze.items()},
        silver_rows={dataset: len(rows) for dataset, rows in valid.items()},
        quarantine_rows={dataset: len(rows) for dataset, rows in quarantine.items()},
        failed_rules=failed_rules,
        trusted_invoice_revenue_eur=decimal_string(invoice_revenue, project_config.money_scale),
    )
    storage_adapter.write_summary(batch_id, summary.as_dict())
    batches = state.setdefault("batches", {})
    batches[batch_id] = {
        "fingerprint": fingerprint,
        "scenario": scenario,
        "status": status,
        "execution_timestamp": timestamp,
    }
    if status == "success":
        state["latest_successful_refresh_timestamp"] = timestamp
    storage_adapter.write_state(state)
    LOGGER.info(
        "Batch processing completed",
        extra={"batch_id": batch_id, "scenario": scenario, "status": status},
    )
    return summary
