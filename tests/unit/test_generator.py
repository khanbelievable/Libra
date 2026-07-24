import json
from pathlib import Path

from datalibra.generators import generate_scenario
from tests.helpers import read_rows


def _files(path: Path) -> dict[str, bytes]:
    return {item.name: item.read_bytes() for item in sorted(path.iterdir()) if item.is_file()}


def test_same_seed_is_byte_reproducible(tmp_path: Path) -> None:
    first = generate_scenario("healthy", tmp_path / "first")
    second = generate_scenario("healthy", tmp_path / "second")
    assert _files(first) == _files(second)


def test_routes_and_costs_have_deterministic_business_relationships(tmp_path: Path) -> None:
    batch = generate_scenario("healthy", tmp_path)
    routes = {row["route_id"]: row for row in read_rows(batch / "routes.csv")}
    shipments = {row["shipment_id"]: row for row in read_rows(batch / "shipments.csv")}
    costs = read_rows(batch / "operational_costs.csv")

    assert len(routes) == 10
    assert len(shipments) == 720
    assert len(costs) == 2880
    assert {row["cost_type"] for row in costs} == {
        "FUEL",
        "LABOR",
        "WAREHOUSING",
        "TRANSPORT",
    }
    assert all(row["route_id"] in routes for row in shipments.values())
    assert all(row["shipment_id"] in shipments for row in costs)
    assert all(row["route_id"] == shipments[row["shipment_id"]]["route_id"] for row in costs)


def test_broken_generators_create_expected_source_failures(tmp_path: Path) -> None:
    duplicate = generate_scenario("duplicate_invoices", tmp_path)
    missing_fx = generate_scenario("missing_gbp_fx", tmp_path)
    incomplete = generate_scenario("incomplete_germany", tmp_path)
    invalid_costs = generate_scenario("invalid_operational_costs", tmp_path)

    assert len(read_rows(duplicate / "invoices.csv")) == 732
    assert len(read_rows(missing_fx / "exchange_rates.csv")) == 1064
    german_invoices = [
        row for row in read_rows(incomplete / "invoices.csv") if row["country_code"] == "DE"
    ]
    assert len(german_invoices) == 43
    assert len(read_rows(invalid_costs / "operational_costs.csv")) == 2880


def test_correction_manifest_declares_healthy_batch_supersession(tmp_path: Path) -> None:
    initial = generate_scenario("cost_correction_initial", tmp_path)
    corrected = generate_scenario("cost_correction_corrected", tmp_path)

    for batch in (initial, corrected):
        manifest = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["batch_id"] == "milestone1-correction"
        assert manifest["supersedes_batch_id"] == "slice001-healthy"
