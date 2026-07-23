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

from datalibra import PIPELINE_VERSION
from datalibra.config import ProjectConfig, load_project_config
from datalibra.domain.contracts import (
    DATA_CONTRACT_VERSION,
    DATE_FIELD,
    FACT_DATASETS,
    IDENTIFIER_FIELDS,
    MONETARY_FIELD,
    SOURCE_FIELDS,
    financial_claim_fingerprint,
    source_fingerprint,
)
from datalibra.domain.errors import (
    ArtifactIntegrityError,
    ClaimsIntegrityError,
    CrossBatchCollisionError,
    StateIntegrityError,
)
from datalibra.domain.integrity import (
    attestation_matches,
    canonical_json_digest,
    rows_attestation,
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
INVOICE_BUSINESS_KEY = ("invoice_id",)


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
    claims: Sequence[dict[str, str]], arrival_sequences: dict[str, int]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Resolve active invoice claims without allowing last-write-wins ownership."""

    by_invoice: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in claims:
        by_invoice[row["invoice_id"]].append(dict(row))

    trusted: list[dict[str, str]] = []
    quarantined: list[dict[str, str]] = []
    for invoice_id in sorted(by_invoice):
        occurrences = sorted(
            by_invoice[invoice_id],
            key=lambda row: (
                arrival_sequences[row["_batch_id"]],
                row["_batch_id"],
                row["_source_row_number"],
            ),
        )
        payloads = {financial_claim_fingerprint(row) for row in occurrences}
        if len(payloads) > 1:
            quarantined.extend(
                {**row, "_reason_codes": "CONFLICTING_DUPLICATE_INVOICE"} for row in occurrences
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


def _arrival_sequences(state: dict[str, Any], batch_id: str) -> tuple[dict[str, int], int, bool]:
    """Return validated active sequences and the current batch's immutable sequence."""

    batches = state.get("batches", {})
    legacy = [
        stored_batch_id
        for stored_batch_id, record in batches.items()
        if not isinstance(record.get("arrival_sequence"), int)
    ]
    migrated_legacy = False
    if legacy:
        if len(batches) == 1 and legacy == [batch_id]:
            batches[batch_id]["arrival_sequence"] = 1
            migrated_legacy = True
        else:
            raise StateIntegrityError(
                "STATE_MIGRATION_REQUIRED: legacy processed state has no reliable arrival "
                "sequence. Archive or clear the processed output and replay all source batches "
                "in their true arrival order."
            )

    sequences = {
        stored_batch_id: int(record["arrival_sequence"])
        for stored_batch_id, record in batches.items()
    }
    if any(sequence <= 0 for sequence in sequences.values()) or len(set(sequences.values())) != len(
        sequences
    ):
        raise StateIntegrityError(
            "STATE_ARRIVAL_SEQUENCE_INVALID: arrival_sequence values must be unique positive "
            "integers. Restore a valid state backup or replay batches into a clean output root."
        )

    if batch_id in sequences:
        current_sequence = sequences[batch_id]
    else:
        current_sequence = max(sequences.values(), default=0) + 1
        sequences[batch_id] = current_sequence
    return sequences, current_sequence, migrated_legacy


def _load_verified_claim_manifests(
    storage: PipelineStorage,
    state: dict[str, Any],
    *,
    current_batch_id: str,
    allow_current_rebuild: bool,
) -> tuple[dict[str, list[dict[str, str]]], bool]:
    """Load independently attested active claim contributions or fail closed."""

    verified: dict[str, list[dict[str, str]]] = {}
    current_rebuild_required = False
    for stored_batch_id, record in state.get("batches", {}).items():
        expected = record.get("invoice_claim_attestation")
        if not isinstance(expected, dict):
            if stored_batch_id == current_batch_id and allow_current_rebuild:
                current_rebuild_required = True
                continue
            raise StateIntegrityError(
                "STATE_CLAIM_ATTESTATION_MISSING: processed state does not attest invoice "
                f"claims for batch {stored_batch_id!r}. Replay that batch from source in an "
                "otherwise valid single-batch legacy workspace, or rebuild the output root in "
                "true arrival order."
            )
        rows = storage.read_batch_claim_manifest("invoices", stored_batch_id)
        if not attestation_matches(rows, expected, business_key=INVOICE_BUSINESS_KEY):
            if stored_batch_id == current_batch_id and allow_current_rebuild:
                current_rebuild_required = True
                continue
            raise ClaimsIntegrityError(
                "CLAIM_MANIFEST_INTEGRITY_FAILED: missing, truncated, duplicated, altered, or "
                f"mis-owned invoice claim contribution for batch {stored_batch_id!r}. Trusted "
                "Silver was not rewritten; restore the manifest or replay into a clean output "
                "root."
            )
        verified[stored_batch_id] = rows
    return verified, current_rebuild_required


def _verify_claim_aggregate(
    storage: PipelineStorage, expected_rows: Sequence[dict[str, str]]
) -> None:
    committed = storage.read_claims("invoices")
    expected = rows_attestation(expected_rows, business_key=INVOICE_BUSINESS_KEY)
    if not attestation_matches(committed, expected, business_key=INVOICE_BUSINESS_KEY):
        raise ClaimsIntegrityError(
            "CLAIM_AGGREGATE_INTEGRITY_FAILED: aggregate invoice claims do not match verified "
            "batch-owned manifests. Trusted Silver was not published."
        )


def _claim_aggregate_matches(
    storage: PipelineStorage, expected_rows: Sequence[dict[str, str]]
) -> bool:
    expected = rows_attestation(expected_rows, business_key=INVOICE_BUSINESS_KEY)
    return attestation_matches(
        storage.read_claims("invoices"),
        expected,
        business_key=INVOICE_BUSINESS_KEY,
    )


def _artifact_attestations(
    storage: PipelineStorage,
    batch_id: str,
    datasets: Sequence[str],
) -> dict[str, Any]:
    """Read and attest every committed artifact required for a no-op."""

    silver = {
        dataset: rows_attestation(
            [row for row in storage.read_silver(dataset) if row.get("_batch_id") == batch_id]
        )
        for dataset in datasets
    }
    quarantine = {
        dataset: rows_attestation(
            [row for row in storage.read_quarantine(dataset) if row.get("_batch_id") == batch_id]
        )
        for dataset in datasets
    }
    quality = rows_attestation(
        [row for row in storage.read_quality() if row.get("batch_id") == batch_id]
    )
    reconciliation = storage.read_reconciliation(batch_id)
    summary = storage.read_summary(batch_id)
    return {
        "silver": silver,
        "quarantine": quarantine,
        "quality": quality,
        "reconciliation_digest": canonical_json_digest(reconciliation),
        "summary_digest": canonical_json_digest(summary),
    }


def _verify_active_artifacts(
    storage: PipelineStorage,
    state: dict[str, Any],
    datasets: Sequence[str],
    *,
    current_batch_id: str,
    allow_current_rebuild: bool,
    allow_inflight_recovery: bool,
) -> bool:
    """Verify prior evidence; return whether the current batch needs rebuilding."""

    current_rebuild_required = False
    for stored_batch_id, record in state.get("batches", {}).items():
        expected = record.get("artifact_attestations")
        if not isinstance(expected, dict):
            if stored_batch_id == current_batch_id and allow_current_rebuild:
                current_rebuild_required = True
                continue
            raise StateIntegrityError(
                "STATE_ARTIFACT_ATTESTATION_MISSING: processed state does not attest required "
                f"run evidence for batch {stored_batch_id!r}. Replay the batch from source or "
                "rebuild the output root in true arrival order."
            )
        try:
            actual = _artifact_attestations(storage, stored_batch_id, datasets)
        except (FileNotFoundError, KeyError, TypeError, ValueError):
            actual = {}
        if actual != expected:
            if allow_inflight_recovery:
                continue
            if stored_batch_id == current_batch_id:
                current_rebuild_required = True
                continue
            raise ArtifactIntegrityError(
                "PRIOR_ARTIFACT_INTEGRITY_FAILED: trusted or audit evidence for active batch "
                f"{stored_batch_id!r} is missing or altered. No new publication occurred; "
                "restore the evidence or replay into a clean output root."
            )
    return current_rebuild_required


def _business_keys(
    rows: Sequence[dict[str, str]], fields: tuple[str, ...]
) -> list[tuple[str, ...]]:
    return sorted(tuple(row[field] for field in fields) for row in rows)


def _quarantine_signatures(rows: Sequence[dict[str, str]]) -> list[tuple[str, str, str]]:
    return sorted(
        (
            row.get("_batch_id", ""),
            row.get("_source_row_number", ""),
            row.get("_reason_codes", ""),
        )
        for row in rows
    )


def _merged_silver_rows(
    existing: Sequence[dict[str, str]],
    batch_id: str,
    incoming: Sequence[dict[str, str]],
    business_key: tuple[str, ...],
) -> list[dict[str, str]]:
    retained = [row for row in existing if row.get("_batch_id") != batch_id]
    merged = {tuple(row[field] for field in business_key): dict(row) for row in retained}
    for row in incoming:
        merged[tuple(row[field] for field in business_key)] = dict(row)
    return [merged[key] for key in sorted(merged)]


def _normalized_record_payload(row: dict[str, str]) -> dict[str, str]:
    return {
        field: value
        for field, value in row.items()
        if field not in {"_batch_id", "_source_row_number", "_reason_codes"}
    }


def _protect_non_invoice_financial_ownership(
    storage: PipelineStorage,
    batch_id: str,
    valid: dict[str, list[dict[str, str]]],
    quarantine: dict[str, list[dict[str, str]]],
    dataset_keys: dict[str, tuple[str, ...]],
) -> None:
    """Retain first owner for exact facts and reject unsupported conflicts."""

    for dataset in ("shipments", "budgets"):
        business_key = dataset_keys[dataset]
        existing_by_key = {
            tuple(row[field] for field in business_key): row
            for row in storage.read_silver(dataset)
            if row.get("_batch_id") != batch_id
        }
        retained_incoming: list[dict[str, str]] = []
        for row in valid[dataset]:
            key = tuple(row[field] for field in business_key)
            existing = existing_by_key.get(key)
            if existing is None:
                retained_incoming.append(row)
                continue
            if _normalized_record_payload(existing) != _normalized_record_payload(row):
                raise CrossBatchCollisionError(
                    "CROSS_BATCH_FINANCIAL_COLLISION: conflicting "
                    f"{dataset} business key {key!r} is already owned by batch "
                    f"{existing.get('_batch_id')!r}. No trusted output or state was changed."
                )
            quarantine[dataset].append({**row, "_reason_codes": "CROSS_BATCH_DUPLICATE_RECORD"})
        valid[dataset] = retained_incoming


def _previous_summary(storage: PipelineStorage, batch_id: str) -> PipelineSummary:
    value = storage.read_summary(batch_id)
    return PipelineSummary(
        batch_id=str(value["batch_id"]),
        scenario=str(value["scenario"]),
        status="already_processed",
        fingerprint=str(value["fingerprint"]),
        pipeline_version=str(value["pipeline_version"]),
        data_contract_version=str(value["data_contract_version"]),
        quality_rules_version=str(value["quality_rules_version"]),
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
    inflight = storage_adapter.read_inflight()
    inflight_recovery = False
    if inflight is not None:
        inflight_recovery = (
            inflight.get("batch_id") == batch_id and inflight.get("fingerprint") == fingerprint
        )
        if not inflight_recovery:
            raise StateIntegrityError(
                "INFLIGHT_RECOVERY_REQUIRED: an interrupted publication exists for batch "
                f"{inflight.get('batch_id')!r}. Retry that exact batch and fingerprint before "
                "processing another delivery."
            )
    arrival_sequences, arrival_sequence, migrated_legacy = _arrival_sequences(state, batch_id)
    prior = state.get("batches", {}).get(batch_id)
    replay_identity = {
        "fingerprint": fingerprint,
        "pipeline_version": PIPELINE_VERSION,
        "data_contract_version": DATA_CONTRACT_VERSION,
        "quality_rules_version": project_config.quality_rules_version,
    }
    allow_current_claim_rebuild = migrated_legacy or prior is not None
    verified_claim_manifests, claim_manifest_rebuild_required = _load_verified_claim_manifests(
        storage_adapter,
        state,
        current_batch_id=batch_id,
        allow_current_rebuild=allow_current_claim_rebuild,
    )
    verified_prior_claims = [
        row
        for stored_batch_id in sorted(
            verified_claim_manifests,
            key=lambda item: (arrival_sequences[item], item),
        )
        for row in verified_claim_manifests[stored_batch_id]
    ]
    claim_aggregate_valid = _claim_aggregate_matches(storage_adapter, verified_prior_claims)
    if not claim_aggregate_valid and verified_claim_manifests:
        LOGGER.warning(
            "CLAIM_AGGREGATE_RECOVERY_REQUIRED: rebuilding aggregate from verified manifests",
            extra={"batch_id": batch_id, "scenario": scenario},
        )
    identity_compatible = prior is not None and all(
        prior.get(key) == value for key, value in replay_identity.items()
    )
    artifact_rebuild_required = _verify_active_artifacts(
        storage_adapter,
        state,
        project_config.ordered_datasets,
        current_batch_id=batch_id,
        allow_current_rebuild=migrated_legacy or not identity_compatible,
        allow_inflight_recovery=inflight_recovery,
    )
    if (
        prior
        and not migrated_legacy
        and not claim_manifest_rebuild_required
        and claim_aggregate_valid
        and not artifact_rebuild_required
        and identity_compatible
    ):
        try:
            previous = _previous_summary(storage_adapter, batch_id)
        except (FileNotFoundError, KeyError, TypeError, ValueError):
            LOGGER.warning(
                "Processed state has no compatible run summary; rebuilding batch",
                extra={"batch_id": batch_id, "scenario": scenario},
            )
        else:
            if inflight_recovery:
                storage_adapter.clear_inflight()
            LOGGER.info(
                "Batch already processed; returning no-op",
                extra={
                    "batch_id": batch_id,
                    "scenario": scenario,
                    "status": "already_processed",
                },
            )
            return previous

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

    _protect_non_invoice_financial_ownership(
        storage_adapter,
        batch_id,
        valid,
        quarantine,
        project_config.dataset_keys,
    )

    current_claim_attestation = rows_attestation(
        valid["invoices"], business_key=INVOICE_BUSINESS_KEY
    )
    inflight_record = {
        "batch_id": batch_id,
        "fingerprint": fingerprint,
        "arrival_sequence": arrival_sequence,
        "invoice_claim_attestation": current_claim_attestation,
    }
    storage_adapter.write_inflight(inflight_record)
    if storage_adapter.read_inflight() != inflight_record:
        raise ArtifactIntegrityError(
            "INFLIGHT_PUBLICATION_FAILED: recovery marker did not read back before claim "
            "publication."
        )
    storage_adapter.replace_batch_claim_manifest("invoices", batch_id, valid["invoices"])
    committed_current_claims = storage_adapter.read_batch_claim_manifest("invoices", batch_id)
    if not attestation_matches(
        committed_current_claims,
        current_claim_attestation,
        business_key=INVOICE_BUSINESS_KEY,
    ):
        raise ClaimsIntegrityError(
            "CLAIM_MANIFEST_PUBLICATION_FAILED: current batch invoice claims did not read back "
            "with the expected count, digest, and business keys."
        )
    verified_claim_manifests[batch_id] = committed_current_claims
    active_claims = [
        row
        for active_batch_id in sorted(
            arrival_sequences, key=lambda item: (arrival_sequences[item], item)
        )
        for row in verified_claim_manifests[active_batch_id]
    ]
    storage_adapter.replace_all_claims("invoices", active_claims)
    _verify_claim_aggregate(storage_adapter, active_claims)
    all_trusted_invoices, all_dedup_quarantine = _resolve_invoice_claims(
        active_claims, arrival_sequences
    )
    valid["invoices"] = [row for row in all_trusted_invoices if row.get("_batch_id") == batch_id]
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

    expected_silver: dict[str, list[dict[str, str]]] = {}
    expected_quarantine: dict[str, list[dict[str, str]]] = {}
    for dataset in project_config.ordered_datasets:
        if dataset == "invoices":
            expected_silver[dataset] = all_trusted_invoices
        else:
            expected_silver[dataset] = _merged_silver_rows(
                storage_adapter.read_silver(dataset),
                batch_id,
                valid[dataset],
                project_config.dataset_keys[dataset],
            )
        prior_quarantine = storage_adapter.read_quarantine(dataset)
        expected_quarantine[dataset] = [
            row for row in prior_quarantine if row.get("_batch_id") != batch_id
        ] + quarantine[dataset]
        if dataset == "invoices":
            expected_quarantine[dataset] = [
                row
                for row in expected_quarantine[dataset]
                if not INVOICE_DEDUP_REASON_CODES.intersection(
                    row.get("_reason_codes", "").split("|")
                )
            ] + all_dedup_quarantine

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

    reconciliation: dict[str, Any] = {"batch_id": batch_id, "datasets": {}}
    committed_silver_by_dataset: dict[str, list[dict[str, str]]] = {}
    committed_quarantine_by_dataset: dict[str, list[dict[str, str]]] = {}
    for dataset in project_config.ordered_datasets:
        committed_silver = storage_adapter.read_silver(dataset)
        committed_quarantine = storage_adapter.read_quarantine(dataset)
        committed_silver_by_dataset[dataset] = committed_silver
        committed_quarantine_by_dataset[dataset] = committed_quarantine
        batch_trusted = [row for row in committed_silver if row.get("_batch_id") == batch_id]
        batch_quarantined = [
            row for row in committed_quarantine if row.get("_batch_id") == batch_id
        ]
        source_count = len(standardized[dataset])
        source_accounted = source_count == len(batch_trusted) + len(batch_quarantined)
        current_keys_match = _business_keys(
            batch_trusted, project_config.dataset_keys[dataset]
        ) == _business_keys(valid[dataset], project_config.dataset_keys[dataset])
        global_keys_match = len(committed_silver) == len(
            expected_silver[dataset]
        ) and _business_keys(
            committed_silver, project_config.dataset_keys[dataset]
        ) == _business_keys(expected_silver[dataset], project_config.dataset_keys[dataset])
        quarantine_match = _quarantine_signatures(committed_quarantine) == _quarantine_signatures(
            expected_quarantine[dataset]
        )
        row_match = (
            source_accounted and current_keys_match and global_keys_match and quarantine_match
        )
        reconciliation["datasets"][dataset] = {
            "source_rows": source_count,
            "committed_batch_trusted_rows": len(batch_trusted),
            "committed_batch_quarantined_rows": len(batch_quarantined),
            "source_rows_accounted": source_accounted,
            "current_business_keys_match": current_keys_match,
            "global_business_keys_match": global_keys_match,
            "quarantine_evidence_matches": quarantine_match,
            "row_count_matches": row_match,
        }
        quality_results.append(
            QualityResult(
                rule_name="SOURCE_TARGET_ROW_RECONCILIATION",
                affected_dataset=dataset,
                batch_id=batch_id,
                failure_reason="" if row_match else "COMMITTED_READBACK_MISMATCH",
                failed_row_count=0 if row_match else 1,
                affected_financial_amount_eur="",
                execution_timestamp=timestamp,
                validation_status="PASS" if row_match else "FAIL",
            )
        )
        if dataset in FACT_DATASETS:
            source_convertible = _sum_eur(standardized[dataset])
            committed_batch_total = _sum_eur(batch_trusted) + _sum_eur(batch_quarantined)
            expected_global_total = _sum_eur(expected_silver[dataset]) + _sum_eur(
                expected_quarantine[dataset]
            )
            committed_global_total = _sum_eur(committed_silver) + _sum_eur(committed_quarantine)
            financial_match = (
                source_convertible == committed_batch_total
                and expected_global_total == committed_global_total
            )
            difference = abs(source_convertible - committed_batch_total) + abs(
                expected_global_total - committed_global_total
            )
            reconciliation["datasets"][dataset].update(
                {
                    "convertible_source_eur": decimal_string(
                        source_convertible, project_config.money_scale
                    ),
                    "committed_batch_trusted_eur": decimal_string(
                        _sum_eur(batch_trusted), project_config.money_scale
                    ),
                    "committed_batch_quarantined_eur": decimal_string(
                        _sum_eur(batch_quarantined), project_config.money_scale
                    ),
                    "committed_global_total_matches": (
                        expected_global_total == committed_global_total
                    ),
                    "financial_total_matches": financial_match,
                }
            )
            quality_results.append(
                QualityResult(
                    rule_name="SOURCE_TARGET_FINANCIAL_RECONCILIATION",
                    affected_dataset=dataset,
                    batch_id=batch_id,
                    failure_reason="" if financial_match else "COMMITTED_FINANCIAL_MISMATCH",
                    failed_row_count=0 if financial_match else 1,
                    affected_financial_amount_eur=(
                        ""
                        if financial_match
                        else decimal_string(difference, project_config.money_scale)
                    ),
                    execution_timestamp=timestamp,
                    validation_status="PASS" if financial_match else "FAIL",
                )
            )

    expected_quality_rows = [result.as_row() for result in quality_results]
    storage_adapter.replace_batch_quality(batch_id, expected_quality_rows)
    committed_quality_rows = [
        row for row in storage_adapter.read_quality() if row.get("batch_id") == batch_id
    ]
    if rows_attestation(committed_quality_rows) != rows_attestation(expected_quality_rows):
        raise ArtifactIntegrityError(
            "QUALITY_EVIDENCE_PUBLICATION_FAILED: committed quality results are missing or "
            "altered. Processed state was not advanced."
        )
    storage_adapter.write_reconciliation(batch_id, reconciliation)
    try:
        committed_reconciliation = storage_adapter.read_reconciliation(batch_id)
    except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
        raise ArtifactIntegrityError(
            "RECONCILIATION_EVIDENCE_PUBLICATION_FAILED: reconciliation evidence is missing "
            "or unreadable. Processed state was not advanced."
        ) from error
    if canonical_json_digest(committed_reconciliation) != canonical_json_digest(reconciliation):
        raise ArtifactIntegrityError(
            "RECONCILIATION_EVIDENCE_PUBLICATION_FAILED: committed reconciliation evidence "
            "does not match the run result. Processed state was not advanced."
        )

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
    committed_batch_silver = {
        dataset: [
            row for row in committed_silver_by_dataset[dataset] if row.get("_batch_id") == batch_id
        ]
        for dataset in project_config.ordered_datasets
    }
    committed_batch_quarantine = {
        dataset: [
            row
            for row in committed_quarantine_by_dataset[dataset]
            if row.get("_batch_id") == batch_id
        ]
        for dataset in project_config.ordered_datasets
    }
    invoice_revenue = _sum_eur(committed_batch_silver["invoices"])
    summary = PipelineSummary(
        batch_id=batch_id,
        scenario=scenario,
        status=status,
        fingerprint=fingerprint,
        pipeline_version=PIPELINE_VERSION,
        data_contract_version=DATA_CONTRACT_VERSION,
        quality_rules_version=project_config.quality_rules_version,
        bronze_rows={dataset: len(rows) for dataset, rows in bronze.items()},
        silver_rows={dataset: len(rows) for dataset, rows in committed_batch_silver.items()},
        quarantine_rows={
            dataset: len(rows)
            for dataset, rows in committed_batch_quarantine.items()
            if dataset in FACT_DATASETS or rows
        },
        failed_rules=failed_rules,
        trusted_invoice_revenue_eur=decimal_string(invoice_revenue, project_config.money_scale),
    )
    storage_adapter.write_summary(batch_id, summary.as_dict())
    try:
        committed_summary = storage_adapter.read_summary(batch_id)
    except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
        raise ArtifactIntegrityError(
            "SUMMARY_EVIDENCE_PUBLICATION_FAILED: run summary is missing or unreadable. "
            "Processed state was not advanced."
        ) from error
    if canonical_json_digest(committed_summary) != canonical_json_digest(summary.as_dict()):
        raise ArtifactIntegrityError(
            "SUMMARY_EVIDENCE_PUBLICATION_FAILED: committed run summary does not match the "
            "pipeline result. Processed state was not advanced."
        )
    batches = state.setdefault("batches", {})
    batches[batch_id] = {
        **replay_identity,
        "arrival_sequence": arrival_sequence,
        "invoice_claim_attestation": current_claim_attestation,
        "scenario": scenario,
        "status": status,
        "execution_timestamp": timestamp,
    }
    for active_batch_id in arrival_sequences:
        batches[active_batch_id]["artifact_attestations"] = _artifact_attestations(
            storage_adapter,
            active_batch_id,
            project_config.ordered_datasets,
        )
    if status == "success":
        state["latest_successful_refresh_timestamp"] = timestamp
    state["next_arrival_sequence"] = max(arrival_sequences.values(), default=0) + 1
    storage_adapter.write_state(state)
    storage_adapter.clear_inflight()
    LOGGER.info(
        "Batch processing completed",
        extra={"batch_id": batch_id, "scenario": scenario, "status": status},
    )
    return summary
