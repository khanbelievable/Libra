"""Load version-controlled JSON configuration without runtime dependencies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProjectConfig:
    """Configuration required by the Slice 001 domain pipeline."""

    repository_root: Path
    reporting_currency: str
    money_scale: Decimal
    rate_scale: Decimal
    expected_invoice_rows_per_country: int
    country_volume_minimum_ratio: Decimal
    dataset_keys: dict[str, tuple[str, ...]]
    ordered_datasets: tuple[str, ...]
    critical_rules: frozenset[str]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value: dict[str, Any] = json.load(handle)
    return value


def discover_repository_root(start: Path | None = None) -> Path:
    """Find the project root using pyproject.toml as the stable marker."""

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise FileNotFoundError("Could not find pyproject.toml from the current directory")


def load_project_config(repository_root: Path | None = None) -> ProjectConfig:
    root = (repository_root or discover_repository_root()).resolve()
    datasets = _read_json(root / "config" / "datasets" / "slice_001.json")
    quality = _read_json(root / "config" / "quality-rules" / "slice_001.json")
    keys = {
        name: tuple(definition["business_key"]) for name, definition in datasets["datasets"].items()
    }
    return ProjectConfig(
        repository_root=root,
        reporting_currency=str(quality["reporting_currency"]),
        money_scale=Decimal(quality["money_scale"]),
        rate_scale=Decimal(quality["rate_scale"]),
        expected_invoice_rows_per_country=int(quality["expected_invoice_rows_per_country"]),
        country_volume_minimum_ratio=Decimal(quality["country_volume_minimum_ratio"]),
        dataset_keys=keys,
        ordered_datasets=tuple(datasets["ordered_datasets"]),
        critical_rules=frozenset(quality["critical_rules"]),
    )
