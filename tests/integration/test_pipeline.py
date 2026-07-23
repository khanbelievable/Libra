from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from tests.helpers import read_rows, refresh_manifest, write_rows


@pytest.mark.integration
def test_missing_manifest_is_rejected_before_any_output(tmp_path: Path) -> None:
    batch = tmp_path / "missing"
    batch.mkdir()

    with pytest.raises(FileNotFoundError, match="Missing batch manifest"):
        process_batch(batch, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.integration
def test_unsafe_batch_identifier_is_rejected(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    manifest_path = batch / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["batch_id"] = "../outside"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="batch_id"):
        process_batch(batch, tmp_path / "output")


@pytest.mark.integration
def test_source_schema_mismatch_is_rejected_before_publication(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    invoices_path = batch / "invoices.csv"
    lines = invoices_path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("invoice_id", "unexpected_id", 1)
    invoices_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    refresh_manifest(batch)

    with pytest.raises(ValueError, match="Schema mismatch"):
        process_batch(batch, tmp_path / "output")


@pytest.mark.integration
def test_manifest_row_count_mismatch_is_rejected_before_publication(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    manifest_path = batch / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["datasets"]["routes"] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="Manifest count mismatch"):
        process_batch(batch, tmp_path / "output")


@pytest.mark.integration
def test_healthy_pipeline_and_unchanged_rerun_are_idempotent(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"

    first = process_batch(batch, output)
    second = process_batch(batch, output)

    assert first.status == "success"
    assert first.silver_rows["invoices"] == 720
    assert first.trusted_invoice_revenue_eur == "916351.47"
    assert second.status == "already_processed"
    assert len(read_rows(output / "silver" / "invoices.csv")) == 720
    state = json.loads((output / "state" / "processed_batches.json").read_text())
    assert state["latest_successful_refresh_timestamp"] == "2026-01-15T08:00:00Z"


@pytest.mark.integration
def test_changed_payload_same_batch_replaces_prior_contribution(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    output = tmp_path / "output"
    original = process_batch(batch, output)
    invoices = read_rows(batch / "invoices.csv")
    invoices[0]["revenue_amount"] = str(Decimal(invoices[0]["revenue_amount"]) + Decimal("100"))
    write_rows(batch / "invoices.csv", "invoices", invoices)
    refresh_manifest(batch)

    corrected = process_batch(batch, output)

    assert corrected.status == "success"
    assert corrected.fingerprint != original.fingerprint
    assert corrected.trusted_invoice_revenue_eur == "916451.47"
    assert len(read_rows(output / "silver" / "invoices.csv")) == 720
    bronze_versions = list((output / "bronze" / "invoices").glob("*.csv"))
    assert len(bronze_versions) == 2
    assert {path.stem for path in bronze_versions} == {
        f"slice001-healthy-{original.fingerprint[:20]}",
        f"slice001-healthy-{corrected.fingerprint[:20]}",
    }


@pytest.mark.integration
def test_deep_output_root_stays_below_practical_windows_path_limit(tmp_path: Path) -> None:
    practical_windows_limit = 260
    target_root_length = 165
    deep_root = tmp_path
    while len(str(deep_root.resolve())) < target_root_length:
        deep_root /= "d"
    batch = generate_scenario("healthy", tmp_path / "input")
    output = deep_root / "processed"

    summary = process_batch(batch, output)

    assert summary.status == "success"
    committed_paths = [path for path in output.rglob("*") if path.is_file()]
    assert committed_paths
    longest_committed_path = max(committed_paths, key=lambda path: len(str(path.resolve())))
    longest_temporary_length = len(str(longest_committed_path.resolve())) + len(".tmp")
    assert longest_temporary_length < practical_windows_limit, (
        f"Longest generated path would be {longest_temporary_length} characters with its "
        f"atomic-write suffix: {longest_committed_path}"
    )


@pytest.mark.integration
def test_missing_required_identifier_is_quarantined(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    invoices = read_rows(batch / "invoices.csv")
    invoices[0]["customer_id"] = ""
    write_rows(batch / "invoices.csv", "invoices", invoices)
    refresh_manifest(batch)

    summary = process_batch(batch, tmp_path / "output")
    quarantine = read_rows(tmp_path / "output" / "quarantine" / "invoices.csv")

    assert summary.status == "quality_failed"
    assert "REQUIRED_IDENTIFIERS" in summary.failed_rules
    assert len(quarantine) == 1
    assert quarantine[0]["_reason_codes"] == "MISSING_CUSTOMER_ID"


@pytest.mark.integration
def test_stale_manifest_is_rejected(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    invoices = read_rows(batch / "invoices.csv")
    invoices[0]["revenue_amount"] = "9999.00"
    write_rows(batch / "invoices.csv", "invoices", invoices)
    with pytest.raises(ValueError, match="fingerprint"):
        process_batch(batch, tmp_path / "output")


@pytest.mark.integration
def test_completely_absent_country_partition_still_fails_volume_rule(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path / "input")
    invoices = [row for row in read_rows(batch / "invoices.csv") if row["country_code"] != "DE"]
    write_rows(batch / "invoices.csv", "invoices", invoices)
    refresh_manifest(batch)

    summary = process_batch(batch, tmp_path / "output")
    quality = read_rows(tmp_path / "output" / "quality" / "quality_results.csv")
    volume = next(row for row in quality if row["rule_name"] == "INVOICE_COUNTRY_VOLUME")

    assert summary.status == "quality_failed"
    assert "INVOICE_COUNTRY_VOLUME" in summary.failed_rules
    assert volume["validation_status"] == "FAIL"
    assert volume["failed_row_count"] == "0"


@pytest.mark.integration
def test_independent_healthy_outputs_are_byte_identical(tmp_path: Path) -> None:
    first_batch = generate_scenario("healthy", tmp_path / "input-a")
    second_batch = generate_scenario("healthy", tmp_path / "input-b")
    first_output = tmp_path / "output-a"
    second_output = tmp_path / "output-b"

    process_batch(first_batch, first_output)
    process_batch(second_batch, second_output)

    def tree_digest(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    assert tree_digest(first_output) == tree_digest(second_output)
