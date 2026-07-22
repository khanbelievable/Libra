from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from datalibra.generators import generate_scenario
from datalibra.silver import process_batch
from tests.helpers import read_rows, refresh_manifest, write_rows


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
    deep_root = tmp_path
    while len(str(deep_root.resolve())) < 145:
        deep_root /= "nested-output-segment"
    batch = generate_scenario("healthy", tmp_path / "input")
    output = deep_root / "processed"

    summary = process_batch(batch, output)

    assert summary.status == "success"
    committed_paths = [path for path in output.rglob("*") if path.is_file()]
    assert committed_paths
    assert max(len(str(path.resolve())) + len(".tmp") for path in committed_paths) < 240


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
