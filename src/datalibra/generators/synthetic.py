"""Generate deterministic, fictional logistics and finance source batches."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

SCENARIOS = ("healthy", "duplicate_invoices", "missing_gbp_fx", "incomplete_germany")
DATASET_ORDER = (
    "countries",
    "currencies",
    "exchange_rates",
    "customers",
    "cost_centers",
    "shipments",
    "invoices",
    "budgets",
)

COUNTRIES = (
    ("DE", "Germany", "EUR"),
    ("NL", "Netherlands", "EUR"),
    ("FR", "France", "EUR"),
    ("GB", "United Kingdom", "GBP"),
    ("TR", "Türkiye", "TRY"),
)
CURRENCIES = (("EUR", "Euro", "2"), ("GBP", "Pound sterling", "2"), ("TRY", "Turkish lira", "2"))

FIELDS = {
    "countries": ("country_code", "country_name", "default_currency"),
    "currencies": ("currency_code", "currency_name", "decimal_places"),
    "exchange_rates": ("rate_date", "currency_code", "rate_to_eur"),
    "customers": ("customer_id", "customer_name", "country_code"),
    "cost_centers": ("cost_center_id", "cost_center_name", "country_code"),
    "shipments": (
        "shipment_id",
        "shipment_date",
        "country_code",
        "customer_id",
        "cost_center_id",
        "currency_code",
        "revenue_amount",
    ),
    "invoices": (
        "invoice_id",
        "shipment_id",
        "invoice_date",
        "country_code",
        "customer_id",
        "cost_center_id",
        "currency_code",
        "revenue_amount",
        "source_updated_at",
    ),
    "budgets": ("month_start", "cost_center_id", "currency_code", "budget_amount"),
}


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _rates() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current = date(2025, 1, 1)
    end = date(2025, 12, 31)
    while current <= end:
        day = current.timetuple().tm_yday
        gbp = Decimal("1.155") + Decimal(day % 17) / Decimal("10000")
        turkish_lira = Decimal("0.0290") - Decimal(day) / Decimal("2000000")
        for currency, rate in (("EUR", Decimal("1")), ("GBP", gbp), ("TRY", turkish_lira)):
            rows.append(
                {
                    "rate_date": current.isoformat(),
                    "currency_code": currency,
                    "rate_to_eur": format(rate.quantize(Decimal("0.000001")), "f"),
                }
            )
        current += timedelta(days=1)
    return rows


def build_datasets(seed: int = 20250101) -> dict[str, list[dict[str, str]]]:
    """Build the healthy source data in memory; all values are fictional."""

    rng = random.Random(seed)
    countries = [
        {"country_code": code, "country_name": name, "default_currency": currency}
        for code, name, currency in COUNTRIES
    ]
    currencies = [
        {"currency_code": code, "currency_name": name, "decimal_places": places}
        for code, name, places in CURRENCIES
    ]
    customers: list[dict[str, str]] = []
    cost_centers: list[dict[str, str]] = []
    for country_code, country_name, _ in COUNTRIES:
        for number in range(1, 5):
            customers.append(
                {
                    "customer_id": f"CUS-{country_code}-{number:03d}",
                    "customer_name": f"{country_name} Customer {number:02d}",
                    "country_code": country_code,
                }
            )
        for number, function in enumerate(("Operations", "Warehousing"), start=1):
            cost_centers.append(
                {
                    "cost_center_id": f"CC-{country_code}-{number:03d}",
                    "cost_center_name": f"{country_name} {function}",
                    "country_code": country_code,
                }
            )

    shipments: list[dict[str, str]] = []
    invoices: list[dict[str, str]] = []
    budgets: list[dict[str, str]] = []
    country_multiplier = {"DE": 1.18, "NL": 1.05, "FR": 1.10, "GB": 0.94, "TR": 18.0}
    currency_by_country = {code: currency for code, _, currency in COUNTRIES}
    shipment_sequence = 1
    for month in range(1, 13):
        for country_code, _, currency in COUNTRIES:
            for local_sequence in range(1, 13):
                shipment_id = f"SHP-2025-{shipment_sequence:06d}"
                invoice_id = f"INV-2025-{shipment_sequence:06d}"
                shipment_date = date(2025, month, 2 + local_sequence)
                invoice_date = shipment_date + timedelta(days=5)
                customer_id = f"CUS-{country_code}-{((local_sequence - 1) % 4) + 1:03d}"
                cost_center_id = f"CC-{country_code}-{((local_sequence - 1) % 2) + 1:03d}"
                base = Decimal(850 + 45 * local_sequence + 17 * month + rng.randint(0, 75))
                local_amount = base * Decimal(str(country_multiplier[country_code]))
                amount = _money(local_amount)
                common = {
                    "country_code": country_code,
                    "customer_id": customer_id,
                    "cost_center_id": cost_center_id,
                    "currency_code": currency,
                    "revenue_amount": amount,
                }
                shipments.append(
                    {
                        "shipment_id": shipment_id,
                        "shipment_date": shipment_date.isoformat(),
                        **common,
                    }
                )
                invoices.append(
                    {
                        "invoice_id": invoice_id,
                        "shipment_id": shipment_id,
                        "invoice_date": invoice_date.isoformat(),
                        **common,
                        "source_updated_at": f"{invoice_date.isoformat()}T06:00:00Z",
                    }
                )
                shipment_sequence += 1
            for cc_number in range(1, 3):
                cost_center_id = f"CC-{country_code}-{cc_number:03d}"
                budget_base = Decimal(18000 + 900 * month + 1250 * cc_number)
                budgets.append(
                    {
                        "month_start": date(2025, month, 1).isoformat(),
                        "cost_center_id": cost_center_id,
                        "currency_code": currency_by_country[country_code],
                        "budget_amount": _money(
                            budget_base * Decimal(str(country_multiplier[country_code]))
                        ),
                    }
                )
    return {
        "countries": countries,
        "currencies": currencies,
        "exchange_rates": _rates(),
        "customers": customers,
        "cost_centers": cost_centers,
        "shipments": shipments,
        "invoices": invoices,
        "budgets": budgets,
    }


def apply_scenario(
    datasets: dict[str, list[dict[str, str]]], scenario: str
) -> dict[str, list[dict[str, str]]]:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario {scenario!r}; expected one of {SCENARIOS}")
    result = {name: [row.copy() for row in rows] for name, rows in datasets.items()}
    if scenario == "duplicate_invoices":
        result["invoices"].extend(row.copy() for row in result["invoices"][:12])
    elif scenario == "missing_gbp_fx":
        result["exchange_rates"] = [
            row
            for row in result["exchange_rates"]
            if not (
                row["currency_code"] == "GBP" and "2025-03-01" <= row["rate_date"] <= "2025-03-31"
            )
        ]
    elif scenario == "incomplete_germany":
        german = [row for row in result["invoices"] if row["country_code"] == "DE"]
        non_german = [row for row in result["invoices"] if row["country_code"] != "DE"]
        result["invoices"] = non_german + german[:43]
        result["invoices"].sort(key=lambda row: row["invoice_id"])
    return result


def _write_csv(path: Path, rows: Iterable[dict[str, str]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _fingerprint(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def generate_scenario(
    scenario: str,
    output_root: Path,
    *,
    seed: int = 20250101,
) -> Path:
    """Generate one batch directory and return it."""

    batch_dir = output_root / scenario
    datasets = apply_scenario(build_datasets(seed), scenario)
    paths: list[Path] = []
    for name in DATASET_ORDER:
        path = batch_dir / f"{name}.csv"
        _write_csv(path, datasets[name], FIELDS[name])
        paths.append(path)
    manifest = {
        "batch_id": f"slice001-{scenario}",
        "scenario": scenario,
        "seed": seed,
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "generated_at": "2026-01-15T08:00:00Z",
        "datasets": {name: len(datasets[name]) for name in DATASET_ORDER},
        "fingerprint": _fingerprint(paths),
    }
    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return batch_dir
