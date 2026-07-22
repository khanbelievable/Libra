from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from datalibra.config import load_project_config


def test_packaged_defaults_match_repository_configuration(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    repository_root = Path(__file__).parents[2]
    repository_config = load_project_config(repository_root)
    monkeypatch.chdir(tmp_path)

    config = load_project_config()

    assert config.reporting_currency == repository_config.reporting_currency
    assert config.dataset_keys == repository_config.dataset_keys
    assert config.ordered_datasets == repository_config.ordered_datasets
    assert config.critical_rules == repository_config.critical_rules
    assert config.quality_rules_version == repository_config.quality_rules_version
