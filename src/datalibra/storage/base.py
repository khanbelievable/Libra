"""Storage protocol implemented locally now and by Delta in a later slice."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class PipelineStorage(Protocol):
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

    def replace_batch_quarantine(
        self, dataset: str, batch_id: str, rows: Sequence[dict[str, str]]
    ) -> None: ...
