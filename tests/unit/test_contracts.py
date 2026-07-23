from __future__ import annotations

from pathlib import Path

import pytest

from datalibra.domain.contracts import financial_claim_fingerprint, fingerprint_storage_id
from datalibra.storage.local import LocalCsvStorage


def test_storage_id_is_stable_80_bit_prefix() -> None:
    fingerprint = "a" * 64
    assert fingerprint_storage_id(fingerprint) == "a" * 20


@pytest.mark.parametrize("fingerprint", ["short", "G" * 64, "a" * 63])
def test_storage_id_rejects_non_sha256_values(fingerprint: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        fingerprint_storage_id(fingerprint)


def test_bronze_short_id_collision_is_never_overwritten(tmp_path: Path) -> None:
    storage = LocalCsvStorage(tmp_path)
    first = "a" * 20 + "b" * 44
    second = "a" * 20 + "c" * 44
    storage.write_bronze(
        "invoices",
        "batch-1",
        first,
        [{"invoice_id": "INV-1", "_source_fingerprint": first}],
    )

    with pytest.raises(RuntimeError, match="collision"):
        storage.write_bronze(
            "invoices",
            "batch-1",
            second,
            [{"invoice_id": "INV-2", "_source_fingerprint": second}],
        )


def test_financial_claim_fingerprint_includes_fx_basis_and_normalized_eur_result() -> None:
    claim = {
        "invoice_id": "INV-1",
        "shipment_id": "SHP-1",
        "invoice_date": "2025-01-07",
        "country_code": "GB",
        "customer_id": "CUS-GB-001",
        "cost_center_id": "CC-GB-001",
        "currency_code": "GBP",
        "revenue_amount": "100.00",
        "fx_rate_to_eur": "1.150000",
        "amount_eur": "115.00",
    }
    changed_rate = {**claim, "fx_rate_to_eur": "1.250000", "amount_eur": "125.00"}
    changed_eur = {**claim, "amount_eur": "114.99"}

    assert financial_claim_fingerprint(claim) != financial_claim_fingerprint(changed_rate)
    assert financial_claim_fingerprint(claim) != financial_claim_fingerprint(changed_eur)
