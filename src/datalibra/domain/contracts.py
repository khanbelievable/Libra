"""Implementation-independent dataset and content contracts for Slice 001."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path

DATASET_ORDER = (
    "countries",
    "currencies",
    "exchange_rates",
    "customers",
    "cost_centers",
    "shipments",
    "invoices",
    "budgets",
)

DATA_CONTRACT_VERSION = "1.2"

SOURCE_FIELDS = {
    "countries": ("country_code", "country_name", "default_currency"),
    "currencies": ("currency_code", "currency_name", "decimal_places"),
    "exchange_rates": ("rate_date", "currency_code", "rate_to_eur"),
    "customers": ("customer_id", "customer_name", "country_code"),
    "cost_centers": ("cost_center_id", "cost_center_name", "country_code"),
    "shipments": (
        "shipment_id",
        "shipment_date",
        "country_code",
        "customer_id",
        "cost_center_id",
        "currency_code",
        "revenue_amount",
    ),
    "invoices": (
        "invoice_id",
        "shipment_id",
        "invoice_date",
        "country_code",
        "customer_id",
        "cost_center_id",
        "currency_code",
        "revenue_amount",
        "source_updated_at",
    ),
    "budgets": ("month_start", "cost_center_id", "currency_code", "budget_amount"),
}

FACT_DATASETS = ("shipments", "invoices", "budgets")
MONETARY_FIELD = {
    "shipments": "revenue_amount",
    "invoices": "revenue_amount",
    "budgets": "budget_amount",
}
DATE_FIELD = {
    "shipments": "shipment_date",
    "invoices": "invoice_date",
    "budgets": "month_start",
}
IDENTIFIER_FIELDS = {
    "shipments": ("shipment_id", "customer_id", "cost_center_id"),
    "invoices": ("invoice_id", "shipment_id", "customer_id", "cost_center_id"),
    "budgets": ("cost_center_id",),
}

INVOICE_BUSINESS_KEY = ("invoice_id",)

INVOICE_FINANCIAL_CLAIM_FIELDS = (
    "invoice_id",
    "shipment_id",
    "invoice_date",
    "country_code",
    "customer_id",
    "cost_center_id",
    "currency_code",
    "revenue_amount",
    "fx_rate_to_eur",
    "amount_eur",
)

STORAGE_ID_HEX_LENGTH = 20


def source_fingerprint(paths: Iterable[Path]) -> str:
    """Return the canonical SHA-256 for a complete source delivery."""

    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        if not path.is_file():
            raise FileNotFoundError(f"Missing source dataset: {path}")
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def fingerprint_storage_id(fingerprint: str) -> str:
    """Return an 80-bit path identifier while full SHA-256 stays in provenance."""

    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("Source fingerprint must be a lowercase SHA-256 hex digest")
    return fingerprint[:STORAGE_ID_HEX_LENGTH]


def canonical_financial_claim_payload(row: dict[str, str]) -> tuple[str, ...]:
    """Return normalized fields that determine invoice identity and EUR result."""

    return tuple(row[field] for field in INVOICE_FINANCIAL_CLAIM_FIELDS)


def financial_claim_fingerprint(row: dict[str, str]) -> str:
    """Hash a normalized invoice claim independently of CSV representation."""

    payload = dict(
        zip(
            INVOICE_FINANCIAL_CLAIM_FIELDS,
            canonical_financial_claim_payload(row),
            strict=True,
        )
    )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()
