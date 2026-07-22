"""Dependency-light Bronze-to-Silver reference implementation."""

from __future__ import annotations

import csv
import json
import logging
import re
from collections import defaultdict
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
    canonical_invoice_payload,
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

INVOICE_DEDUP_REASON_CODES = frozenset(
    {
        "DUPLICATE_INVOICE",
        "CROSS_BATCH_DUPLICATE_INVOICE",
        "CONFLICTING_DUPLICATE_INVOICE",
    }
)


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


def _standardize_dimension(dataset: str, row: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    result = dict(row)
    reasons: list[str] = []
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
        try:
            result["rate_date"] = normalize_date(result["rate_date"])
            rate = parse_decimal(result["rate_to_eur"])
            if rate <= 0:
                raise ValueError("Exchange rate must be greater than zero")
            result["rate_to_eur"] = decimal_string(rate, Decimal("0.000001"))
        except ValueError:
            reasons.append("INVALID_EXCHANGE_RATE")
            result["rate_to_eur"] = ""
    return result, reasons


def _standardize_fact(
    dataset: str, row: dict[str, str], config: ProjectConfig
) -> tuple[dict[str, str], list[str]]:
    result = dict(row)
    reasons: list[str] = []
    if "country_code" in result:
        result["country_code"] = normalize_country(result["country_code"])
    result["currency_code"] = normalize_code(result["currency_code"])
    result[DATE_FIELD[dataset]] = normalize_date(result[DATE_FIELD[dataset]])
    for identifier in IDENTIFIER_FIELDS[dataset]:
        result[identifier] = normalize_identifier(result.get(identifier, ""))
    money_field = MONETARY_FIELD[dataset]
    try:
        amount = parse_decimal(result[money_field])
        if amount < 0:
            raise ValueError(f"{money_field} cannot be negative")
        result[money_field] = decimal_string(amount, config.money_scale)
    except ValueError:
        reasons.append("INVALID_FINANCIAL_VALUE")
        result[money_field] = ""
    return result, reasons


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


def _resolve_invoice_claims(
    claims: Sequence[dict[str, str]], batch_order: Sequence[str]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Resolve active invoice claims without allowing last-write-wins ownership."""

    rank = {batch_id: index for index, batch_id in enumerate(batch_order)}
    by_invoice: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in claims:
        by_invoice[row["invoice_id"]].append(dict(row))

    trusted: list[dict[str, str]] = []
    quarantined: list[dict[str, str]] = []
    for invoice_id in sorted(by_invoice):
        occurrences = sorted(
            by_invoice[invoice_id],
            key=lambda row: (
                rank[row["_batch_id"]],
                row["_source_row_number"],
            ),
        )
        payloads = {canonical_invoice_payload(row) for row in occurrences}
        if len(payloads) > 1:
            quarantined.extend(
                {**row, "_reason_codes": "CONFLICTING_DUPLICATE_INVOICE"}
                for row in occurrences
            )
            continue

        owner = occurrences[0]
        trusted.append(owner)
        for row in occurrences[1:]:
            reason = (
                "DUPLICATE_INVOICE"
                if row["_batch_id"] == owner["_batch_id"]
                else "CROSS_BATCH_DUPLICATE_INVOICE"
            )
            quarantined.append({**row, "_reason_codes": reason})
    return trusted, quarantined


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
    reasons_by_dataset: dict[str, list[list[str]]] = {}
    for dataset in project_config.ordered_datasets:
        standardized[dataset] = []
        reasons_by_dataset[dataset] = []
        for number, row in enumerate(raw[dataset], start=1):
            if dataset in FACT_DATASETS:
                normalized, reasons = _standardize_fact(dataset, row, project_config)
            else:
                normalized, reasons = _standardize_dimension(dataset, row)
            standardized[dataset].append(
                {
                    **normalized,
                    "_batch_id": batch_id,
                    "_source_row_number": f"{number:08d}",
                }
            )
            reasons_by_dataset[dataset].append(reasons)

    country_codes = {row["country_code"] for row in standardized["countries"]}
    currency_codes = {row["currency_code"] for row in standardized["currencies"]}
    for index, row in enumerate(standardized["countries"]):
        if row["default_currency"] not in currency_codes:
            reasons_by_dataset["countries"][index].append("UNKNOWN_CURRENCY_CODE")
    for dataset in ("customers", "cost_centers"):
        for index, row in enumerate(standardized[dataset]):
            if row["country_code"] not in country_codes:
                reasons_by_dataset[dataset][index].append("UNKNOWN_COUNTRY_CODE")
    for index, row in enumerate(standardized["exchange_rates"]):
        if row["currency_code"] not in currency_codes:
            reasons_by_dataset["exchange_rates"][index].append("UNKNOWN_CURRENCY_CODE")

    rate_indices_by_key: dict[tuple[str, str], list[int]] = {}
    for index, row in enumerate(standardized["exchange_rates"]):
        key = (row["rate_date"], row["currency_code"])
        rate_indices_by_key.setdefault(key, []).append(index)
    conflicting_rate_keys: set[tuple[str, str]] = set()
    for key, indices in rate_indices_by_key.items():
        if len(indices) < 2:
            continue
        rates_for_key = {
            standardized["exchange_rates"][index]["rate_to_eur"]
            for index in indices
            if not reasons_by_dataset["exchange_rates"][index]
        }
        has_invalid_occurrence = any(
            reasons_by_dataset["exchange_rates"][index] for index in indices
        )
        if has_invalid_occurrence or len(rates_for_key) != 1:
            conflicting_rate_keys.add(key)
            for index in indices:
                reasons_by_dataset["exchange_rates"][index].append("CONFLICTING_EXCHANGE_RATE")
        else:
            for index in indices[1:]:
                reasons_by_dataset["exchange_rates"][index].append("DUPLICATE_EXCHANGE_RATE")

    customer_ids = {
        row["customer_id"]
        for row, reasons in zip(
            standardized["customers"], reasons_by_dataset["customers"], strict=True
        )
        if not reasons
    }
    cost_center_ids = {
        row["cost_center_id"]
        for row, reasons in zip(
            standardized["cost_centers"], reasons_by_dataset["cost_centers"], strict=True
        )
        if not reasons
    }
    shipment_ids = {row["shipment_id"] for row in standardized["shipments"]}
    invalid_rate_keys = {
        (row["rate_date"], row["currency_code"])
        for row, reasons in zip(
            standardized["exchange_rates"],
            reasons_by_dataset["exchange_rates"],
            strict=True,
        )
        if "INVALID_EXCHANGE_RATE" in reasons
    }
    rates = {
        (row["rate_date"], row["currency_code"]): parse_decimal(row["rate_to_eur"])
        for row, reasons in zip(
            standardized["exchange_rates"],
            reasons_by_dataset["exchange_rates"],
            strict=True,
        )
        if not reasons
    }
    invoice_ids_by_country: dict[str, set[str]] = {country: set() for country in country_codes}
    for row in standardized["invoices"]:
        if row["country_code"] in invoice_ids_by_country:
            invoice_ids_by_country[row["country_code"]].add(row["invoice_id"])
    minimum = (
        Decimal(project_config.expected_invoice_rows_per_country)
        * project_config.country_volume_minimum_ratio
    )
    dropped_countries = {
        country
        for country, invoice_ids in invoice_ids_by_country.items()
        if Decimal(len(invoice_ids)) < minimum
    }
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
            if "country_code" in row and row["country_code"] not in country_codes:
                reasons.append("UNKNOWN_COUNTRY_CODE")
            if row["currency_code"] not in currency_codes:
                reasons.append("UNKNOWN_CURRENCY_CODE")
            if dataset == "invoices":
                if row["shipment_id"] not in shipment_ids:
                    reasons.append("UNKNOWN_SHIPMENT_ID")
                if row["country_code"] in dropped_countries:
                    reasons.append("COUNTRY_VOLUME_DROP")
            rate_key = (row[DATE_FIELD[dataset]], row["currency_code"])
            rate = rates.get(rate_key)
            if not row[MONETARY_FIELD[dataset]] or "UNKNOWN_CURRENCY_CODE" in reasons:
                row["fx_rate_to_eur"] = ""
                row["amount_eur"] = ""
            elif rate_key in conflicting_rate_keys:
                reasons.append("CONFLICTING_EXCHANGE_RATE_REFERENCE")
                row["fx_rate_to_eur"] = ""
                row["amount_eur"] = ""
            elif rate_key in invalid_rate_keys:
                reasons.append("INVALID_EXCHANGE_RATE_REFERENCE")
                row["fx_rate_to_eur"] = ""
                row["amount_eur"] = ""
            elif rate is None:
                reasons.append("MISSING_EXCHANGE_RATE")
                row["fx_rate_to_eur"] = ""
                row["amount_eur"] = ""
            else:
                row["fx_rate_to_eur"] = decimal_string(rate, project_config.rate_scale)
                row["amount_eur"] = decimal_string(
                    parse_decimal(row[MONETARY_FIELD[dataset]]) * rate,
                    project_config.money_scale,
                )

    valid: dict[str, list[dict[str, str]]] = {}
    quarantine: dict[str, list[dict[str, str]]] = {}
    for dataset in project_config.ordered_datasets:
        valid[dataset] = []
        quarantine[dataset] = []
        for row, reasons in zip(standardized[dataset], reasons_by_dataset[dataset], strict=True):
            if reasons:
                quarantine[dataset].append({**row, "_reason_codes": "|".join(sorted(set(reasons)))})
            else:
                valid[dataset].append(row)

    storage_adapter.replace_batch_claims("invoices", batch_id, valid["invoices"])
    active_batch_order = list(state.get("batches", {}))
    if batch_id not in active_batch_order:
        active_batch_order.append(batch_id)
    active_batches = set(active_batch_order)
    active_claims = [
        row
        for row in storage_adapter.read_claims("invoices")
        if row.get("_batch_id") in active_batches
    ]
    all_trusted_invoices, all_dedup_quarantine = _resolve_invoice_claims(
        active_claims, active_batch_order
    )
    valid["invoices"] = [
        row for row in all_trusted_invoices if row.get("_batch_id") == batch_id
    ]
    quarantine["invoices"].extend(
        row for row in all_dedup_quarantine if row.get("_batch_id") == batch_id
    )

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
        if dataset == "invoices":
            storage_adapter.replace_all_silver(
                dataset, all_trusted_invoices, project_config.dataset_keys[dataset]
            )
        else:
            storage_adapter.replace_batch_and_merge_silver(
                dataset,
                batch_id,
                valid[dataset],
                project_config.dataset_keys[dataset],
            )
        storage_adapter.replace_batch_quarantine(dataset, batch_id, quarantine[dataset])
    storage_adapter.replace_dedup_quarantine(
        "invoices", all_dedup_quarantine, INVOICE_DEDUP_REASON_CODES
    )
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
        quarantine_rows={
            dataset: len(rows)
            for dataset, rows in quarantine.items()
            if dataset in FACT_DATASETS or rows
        },
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
