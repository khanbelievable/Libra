"""Storage protocol implemented locally now and by Delta in a later slice."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PipelineStorage(Protocol):
    """Complete publication and read-back contract used by orchestration.

    Implementations must make each individual write atomic. Orchestration writes
    processed state last so an interrupted publication is recoverable by replay.
    """

    def write_bronze(
        self,
        dataset: str,
        batch_id: str,
        fingerprint: str,
        rows: Sequence[dict[str, str]],
    ) -> None: ...

    def replace_batch_and_merge_silver(
        self,
        dataset: str,
        batch_id: str,
        rows: Sequence[dict[str, str]],
        business_key: tuple[str, ...],
    ) -> None: ...

    def replace_all_silver(
        self,
        dataset: str,
        rows: Sequence[dict[str, str]],
        business_key: tuple[str, ...],
    ) -> None: ...

    def replace_batch_quarantine(
        self, dataset: str, batch_id: str, rows: Sequence[dict[str, str]]
    ) -> None: ...

    def replace_batch_quality(self, batch_id: str, rows: Sequence[dict[str, str]]) -> None: ...

    def replace_batch_claims(
        self, dataset: str, batch_id: str, rows: Sequence[dict[str, str]]
    ) -> None: ...

    def read_claims(self, dataset: str) -> list[dict[str, str]]: ...

    def replace_dedup_quarantine(
        self,
        dataset: str,
        rows: Sequence[dict[str, str]],
        reason_codes: frozenset[str],
    ) -> None: ...

    def read_bronze(
        self, dataset: str, batch_id: str, fingerprint: str
    ) -> list[dict[str, str]]: ...

    def read_silver(self, dataset: str) -> list[dict[str, str]]: ...

    def read_quarantine(self, dataset: str) -> list[dict[str, str]]: ...

    def read_quality(self) -> list[dict[str, str]]: ...

    def read_state(self) -> dict[str, Any]: ...

    def write_state(self, state: dict[str, Any]) -> None: ...

    def write_reconciliation(self, batch_id: str, value: dict[str, Any]) -> None: ...

    def write_summary(self, batch_id: str, value: dict[str, Any]) -> None: ...

    def read_summary(self, batch_id: str) -> dict[str, Any]: ...
