from __future__ import annotations

from pathlib import Path

import pytest

from datalibra.domain.contracts import fingerprint_storage_id
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
