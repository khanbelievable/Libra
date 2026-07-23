"""Generate deterministic, fictional logistics and finance source batches."""

from __future__ import annotations

import csv
import json
import random
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from datalibra.domain.contracts import DATASET_ORDER, SOURCE_FIELDS, source_fingerprint

SCENARIOS = (
    "healthy",
    "duplicate_invoices",
    "missing_gbp_fx",
    "incomplete_germany",
    "invalid_operational_costs",
    "cost_correction_initial",
    "cost_correction_corrected",
)

COUNTRIES = (
    ("DE", "Germany", "EUR"),
    ("NL", "Netherlands", "EUR"),
    ("FR", "France", "EUR"),
    ("GB", "United Kingdom", "GBP"),
    ("TR", "Türkiye", "TRY"),
)
CURRENCIES = (("EUR", "Euro", "2"), ("GBP", "Pound sterling", "2"), ("TRY", "Turkish lira", "2"))
ROUTES = (
    ("RTE-DE-NL-ROAD", "DE", "NL", "ROAD", "575.00", "1"),
    ("RTE-DE-FR-RAIL", "DE", "FR", "RAIL", "880.00", "2"),
    ("RTE-NL-DE-ROAD", "NL", "DE", "ROAD", "575.00", "1"),
    ("RTE-NL-GB-SEA", "NL", "GB", "SEA", "520.00", "3"),
    ("RTE-FR-DE-ROAD", "FR", "DE", "ROAD", "900.00", "2"),
    ("RTE-FR-NL-RAIL", "FR", "NL", "RAIL", "520.00", "2"),
    ("RTE-GB-NL-SEA", "GB", "NL", "SEA", "500.00", "3"),
    ("RTE-GB-FR-ROAD", "GB", "FR", "ROAD", "460.00", "2"),
    ("RTE-TR-DE-ROAD", "TR", "DE", "ROAD", "2500.00", "5"),
    ("RTE-TR-NL-SEA", "TR", "NL", "SEA", "2800.00", "8"),
)


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

    routes = [
        {
            "route_id": route_id,
            "origin_country_code": origin,
            "destination_country_code": destination,
            "transport_mode": mode,
            "distance_km": distance,
            "standard_transit_days": transit_days,
        }
        for route_id, origin, destination, mode, distance, transit_days in ROUTES
    ]
    routes_by_origin: dict[str, list[dict[str, str]]] = {}
    for route in routes:
        routes_by_origin.setdefault(route["origin_country_code"], []).append(route)

    shipments: list[dict[str, str]] = []
    invoices: list[dict[str, str]] = []
    budgets: list[dict[str, str]] = []
    operational_costs: list[dict[str, str]] = []
    country_multiplier = {"DE": 1.18, "NL": 1.05, "FR": 1.10, "GB": 0.94, "TR": 18.0}
    local_currency_factor = {
        "DE": Decimal("1.00"),
        "NL": Decimal("1.00"),
        "FR": Decimal("1.00"),
        "GB": Decimal("0.86"),
        "TR": Decimal("35.00"),
    }
    warehouse_rate = {
        "DE": Decimal("6.50"),
        "NL": Decimal("7.00"),
        "FR": Decimal("6.00"),
        "GB": Decimal("7.50"),
        "TR": Decimal("4.00"),
    }
    mode_rates = {
        "ROAD": {
            "FUEL": Decimal("0.060"),
            "TRANSPORT": Decimal("0.120"),
            "LABOR": Decimal("25.00"),
        },
        "RAIL": {
            "FUEL": Decimal("0.030"),
            "TRANSPORT": Decimal("0.080"),
            "LABOR": Decimal("20.00"),
        },
        "SEA": {
            "FUEL": Decimal("0.020"),
            "TRANSPORT": Decimal("0.060"),
            "LABOR": Decimal("15.00"),
        },
    }
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
                route = routes_by_origin[country_code][(local_sequence - 1) % 2]
                route_id = route["route_id"]
                volume = Decimal("8.00") + Decimal(local_sequence) * Decimal("0.70")
                volume += Decimal(month % 3) * Decimal("0.40")
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
                        "route_id": route_id,
                        "volume_m3": _money(volume),
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
                distance = Decimal(route["distance_km"])
                transit_days = Decimal(route["standard_transit_days"])
                mode = route["transport_mode"]
                volume_factor = Decimal("0.75") + volume / Decimal("20")
                cost_eur = {
                    "FUEL": distance * mode_rates[mode]["FUEL"] * volume_factor,
                    "LABOR": transit_days
                    * mode_rates[mode]["LABOR"]
                    * (Decimal("0.80") + volume / Decimal("30")),
                    "WAREHOUSING": volume * warehouse_rate[country_code],
                    "TRANSPORT": distance
                    * mode_rates[mode]["TRANSPORT"]
                    * (Decimal("0.85") + volume / Decimal("40")),
                }
                for cost_type, eur_value in cost_eur.items():
                    operational_costs.append(
                        {
                            "cost_id": f"CST-{shipment_sequence:06d}-{cost_type[:3]}",
                            "shipment_id": shipment_id,
                            "route_id": route_id,
                            "cost_center_id": cost_center_id,
                            "country_code": country_code,
                            "posting_date": (shipment_date + timedelta(days=3)).isoformat(),
                            "cost_type": cost_type,
                            "amount": _money(eur_value * local_currency_factor[country_code]),
                            "currency_code": currency,
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
        "routes": routes,
        "shipments": shipments,
        "invoices": invoices,
        "budgets": budgets,
        "operational_costs": operational_costs,
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
    elif scenario == "invalid_operational_costs":
        invalid = result["operational_costs"]
        invalid[0]["route_id"] = "RTE-UNKNOWN"
        invalid[1]["shipment_id"] = "SHP-UNKNOWN"
        invalid[2]["cost_center_id"] = "CC-UNKNOWN"
        invalid[3]["country_code"] = "ZZ"
        invalid[4]["currency_code"] = "USD"
        invalid[5]["posting_date"] = "2026-01-15"
        invalid[6]["amount"] = "NaN"
        invalid[7]["amount"] = "-10.00"
        invalid[8]["cost_type"] = "OTHER"
    elif scenario == "cost_correction_initial":
        result["operational_costs"] = result["operational_costs"][1:]
    return result


def _write_csv(path: Path, rows: Iterable[dict[str, str]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


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
        _write_csv(path, datasets[name], SOURCE_FIELDS[name])
        paths.append(path)
    batch_id = (
        "milestone1-correction"
        if scenario in {"cost_correction_initial", "cost_correction_corrected"}
        else (
            "milestone1-invalid-operational-costs"
            if scenario == "invalid_operational_costs"
            else f"slice001-{scenario}"
        )
    )
    manifest = {
        "batch_id": batch_id,
        "scenario": scenario,
        "seed": seed,
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "generated_at": "2026-01-15T08:00:00Z",
        "datasets": {name: len(datasets[name]) for name in DATASET_ORDER},
        "fingerprint": source_fingerprint(paths),
    }
    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return batch_dir
