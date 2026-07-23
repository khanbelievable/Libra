"""Deterministic attestations for persisted row and JSON evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any


def canonical_json_digest(value: Any) -> str:
    """Return SHA-256 over a stable UTF-8 JSON representation."""

    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def rows_attestation(
    rows: Sequence[dict[str, str]],
    *,
    business_key: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Attest exact canonical rows and, when supplied, their business keys."""

    canonical_rows = sorted(
        (dict(sorted(row.items())) for row in rows),
        key=lambda row: json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ),
    )
    result: dict[str, Any] = {
        "count": len(canonical_rows),
        "digest": canonical_json_digest(canonical_rows),
    }
    if business_key:
        keys = sorted(tuple(row[field] for field in business_key) for row in canonical_rows)
        result["business_keys_digest"] = canonical_json_digest(keys)
    return result


def attestation_matches(
    rows: Sequence[dict[str, str]],
    expected: dict[str, Any],
    *,
    business_key: tuple[str, ...] = (),
) -> bool:
    """Return whether rows match an independently persisted attestation."""

    return rows_attestation(rows, business_key=business_key) == expected
