from pathlib import Path

from datalibra.generators import generate_scenario
from tests.helpers import read_rows


def _files(path: Path) -> dict[str, bytes]:
    return {item.name: item.read_bytes() for item in sorted(path.iterdir()) if item.is_file()}


def test_same_seed_is_byte_reproducible(tmp_path: Path) -> None:
    first = generate_scenario("healthy", tmp_path / "first")
    second = generate_scenario("healthy", tmp_path / "second")
    assert _files(first) == _files(second)


def test_broken_generators_create_expected_source_failures(tmp_path: Path) -> None:
    duplicate = generate_scenario("duplicate_invoices", tmp_path)
    missing_fx = generate_scenario("missing_gbp_fx", tmp_path)
    incomplete = generate_scenario("incomplete_germany", tmp_path)

    assert len(read_rows(duplicate / "invoices.csv")) == 732
    assert len(read_rows(missing_fx / "exchange_rates.csv")) == 1064
    german_invoices = [
        row for row in read_rows(incomplete / "invoices.csv") if row["country_code"] == "DE"
    ]
    assert len(german_invoices) == 43
