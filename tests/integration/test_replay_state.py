from __future__ import annotations

import json
from pathlib import Path

import pytest

from datalibra import PIPELINE_VERSION
from datalibra.domain.contracts import DATA_CONTRACT_VERSION
from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from datalibra.storage.local import LocalCsvStorage


class SummaryCrashStorage(LocalCsvStorage):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.fail_next_summary = True

    def write_summary(self, batch_id: str, value: dict[str, object]) -> None:
        if self.fail_next_summary:
            self.fail_next_summary = False
            raise OSError("simulated crash before state commit")
        super().write_summary(batch_id, value)


@pytest.mark.integration
@pytest.mark.parametrize(
    "version_field",
    ["pipeline_version", "data_contract_version", "quality_rules_version"],
)
def test_changed_processing_identity_forces_reprocessing(
    tmp_path: Path, version_field: str
) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"
    first = process_batch(batch, output)
    state_path = output / "state" / "processed_batches.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["batches"][first.batch_id][version_field] = "obsolete"
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rebuilt = process_batch(batch, output)
    committed_state = json.loads(state_path.read_text(encoding="utf-8"))
    committed = committed_state["batches"][first.batch_id]

    assert rebuilt.status == "success"
    assert committed["pipeline_version"] == PIPELINE_VERSION
    assert committed["data_contract_version"] == DATA_CONTRACT_VERSION
    assert committed["quality_rules_version"] == rebuilt.quality_rules_version


@pytest.mark.integration
def test_missing_run_summary_is_rebuilt_instead_of_returning_false_noop(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"
    first = process_batch(batch, output)
    summary_path = output / "runs" / f"{first.batch_id}.json"
    summary_path.unlink()

    rebuilt = process_batch(batch, output)

    assert rebuilt.status == "success"
    assert summary_path.is_file()


@pytest.mark.integration
def test_state_is_committed_last_and_interrupted_run_is_replayable(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"
    storage = SummaryCrashStorage(output)

    with pytest.raises(OSError, match="simulated crash"):
        process_batch(batch, output, storage=storage)

    state_path = output / "state" / "processed_batches.json"
    assert not state_path.exists()

    recovered = process_batch(batch, output, storage=storage)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert recovered.status == "success"
    assert state["batches"][recovered.batch_id]["status"] == "success"
