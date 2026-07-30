"""Export approved Databricks Silver outputs as a governed CSV package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from datalibra.snowflake.contracts import CONTRACT_VERSION

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _qualified(catalog: str, schema: str, table: str) -> str:
    if not all(IDENTIFIER.fullmatch(value) for value in (catalog, schema, table)):
        raise ValueError("Catalog, schema, and table names must be simple SQL identifiers")
    return f"`{catalog}`.`{schema}`.`{table}`"


def export_queries(catalog: str, schema: str) -> dict[str, str]:
    """Return the exact, version-controlled Databricks-side export queries."""

    def table(name: str) -> str:
        return _qualified(catalog, schema, name)

    provenance = "_batch_id, _source_fingerprint"
    return {
        "countries": (
            f"SELECT country_code,country_name,default_currency,{provenance} "
            f"FROM {table('silver_countries')} ORDER BY country_code"
        ),
        "currencies": (
            f"SELECT currency_code,currency_name,decimal_places,{provenance} "
            f"FROM {table('silver_currencies')} ORDER BY currency_code"
        ),
        "customers": (
            f"SELECT customer_id,customer_name,country_code,{provenance} "
            f"FROM {table('silver_customers')} ORDER BY customer_id"
        ),
        "cost_centers": (
            f"SELECT cost_center_id,cost_center_name,country_code,{provenance} "
            f"FROM {table('silver_cost_centers')} ORDER BY cost_center_id"
        ),
        "routes": (
            "SELECT route_id,origin_country_code,destination_country_code,transport_mode,"
            f"distance_km,standard_transit_days,{provenance} FROM {table('silver_routes')} "
            "ORDER BY route_id"
        ),
        "shipments": (
            "SELECT shipment_id,shipment_date,route_id,volume_m3,country_code,customer_id,"
            "cost_center_id,currency_code,revenue_amount,fx_rate_to_eur,amount_eur,"
            "_batch_id,_source_fingerprint,_source_file,_source_row_number "
            f"FROM {table('silver_shipments')} ORDER BY shipment_id"
        ),
        "invoices": (
            "WITH R AS (SELECT DATE_TRUNC('MONTH',rate_date) month_start,currency_code,"
            "rate_to_eur,ROW_NUMBER() OVER(PARTITION BY DATE_TRUNC('MONTH',rate_date),"
            "currency_code ORDER BY rate_date) rn "
            f"FROM {table('silver_exchange_rates')}) "
            "SELECT I.invoice_id,I.shipment_id,I.invoice_date,I.country_code,I.customer_id,"
            "I.cost_center_id,I.currency_code,I.revenue_amount,I.fx_rate_to_eur,I.amount_eur,"
            "CAST(I.revenue_amount*R.rate_to_eur AS DECIMAL(20,2)) "
            "amount_at_comparison_rate_eur,I.source_updated_at,I._batch_id,"
            "I._source_fingerprint,I._source_file,I._source_row_number "
            f"FROM {table('silver_invoices')} I JOIN R ON R.rn=1 "
            "AND R.month_start=DATE_TRUNC('MONTH',I.invoice_date) "
            "AND R.currency_code=I.currency_code ORDER BY I.invoice_id"
        ),
        "operational_costs": (
            "SELECT cost_id,shipment_id,route_id,cost_center_id,country_code,posting_date,"
            "cost_type,amount,currency_code,fx_rate_to_eur,amount_eur,_batch_id,"
            "_source_fingerprint,_source_file,_source_row_number "
            f"FROM {table('silver_operational_costs')} ORDER BY cost_id"
        ),
        "budgets": (
            "SELECT month_start,cost_center_id,currency_code,budget_amount,fx_rate_to_eur,"
            "amount_eur,_batch_id,_source_fingerprint,_source_file,_source_row_number "
            f"FROM {table('silver_budgets')} ORDER BY month_start,cost_center_id"
        ),
        "data_quality_results": (
            "SELECT batch_id,affected_dataset,rule_name,validation_status,failure_reason,"
            "failed_row_count,affected_financial_amount_eur,execution_timestamp,"
            "MAX(CASE WHEN validation_status='PASS' THEN execution_timestamp END) OVER() "
            "latest_successful_refresh_timestamp,SHA2(batch_id,256) _source_fingerprint "
            f"FROM {table('quality_results')} ORDER BY batch_id,affected_dataset,rule_name"
        ),
    }


class DatabricksCli:
    """Small wrapper around an existing authenticated Databricks CLI profile."""

    def __init__(self, executable: Path, profile: str, warehouse_id: str) -> None:
        self.executable = executable
        self.profile = profile
        self.warehouse_id = warehouse_id

    def _api(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Any:
        command = [
            str(self.executable),
            "api",
            method,
            path,
            "--profile",
            self.profile,
        ]
        if payload is not None:
            command.extend(("--json", json.dumps(payload, separators=(",", ":"))))
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        return json.loads(completed.stdout)

    def query(self, statement: str) -> tuple[list[str], list[list[Any]]]:
        response = self._api(
            "post",
            "/api/2.0/sql/statements/",
            {
                "warehouse_id": self.warehouse_id,
                "statement": statement,
                "wait_timeout": "50s",
                "disposition": "INLINE",
                "format": "JSON_ARRAY",
            },
        )
        statement_id = response["statement_id"]
        while response["status"]["state"] in {"PENDING", "RUNNING"}:
            time.sleep(1)
            response = self._api("get", f"/api/2.0/sql/statements/{statement_id}")
        if response["status"]["state"] != "SUCCEEDED":
            raise RuntimeError(f"Databricks statement failed: {response['status']['state']}")
        columns = [column["name"] for column in response["manifest"]["schema"]["columns"]]
        return columns, response.get("result", {}).get("data_array", [])


def build_package(
    client: DatabricksCli,
    catalog: str,
    schema: str,
    output: Path,
    load_id: str,
    exported_at: str | None = None,
) -> Path:
    """Write deterministic extracts followed by their owning manifest."""

    output.mkdir(parents=True, exist_ok=False)
    items = []
    checksums = []
    for source_table, query in export_queries(catalog, schema).items():
        columns, rows = client.query(query)
        csv_path = output / f"{source_table}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(columns)
            writer.writerows(rows)
        checksum = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        checksums.append(f"{source_table}:{checksum}")
        financial_index = columns.index("amount_eur") if "amount_eur" in columns else None
        total = (
            sum((Decimal(str(row[financial_index])) for row in rows), start=Decimal("0"))
            if financial_index is not None
            else None
        )
        items.append(
            {
                "source_table": source_table,
                "source_row_count": len(rows),
                "source_financial_total": str(total) if total is not None else None,
                "sha256": checksum,
            }
        )
    fingerprint = hashlib.sha256("\n".join(checksums).encode()).hexdigest()
    manifest = {
        "load_id": load_id,
        "contract_version": CONTRACT_VERSION,
        "load_timestamp": exported_at or datetime.now(UTC).isoformat(),
        "source_fingerprint": fingerprint,
        "status": "EXPORTED",
        "items": items,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output / "manifest.json"


def main(argv: Sequence[str] | None = None) -> int:
    command = argparse.ArgumentParser(description="Export governed Databricks outputs")
    command.add_argument("--databricks", type=Path, required=True)
    command.add_argument("--profile", default="LIBRA")
    command.add_argument("--warehouse-id", required=True)
    command.add_argument("--catalog", required=True)
    command.add_argument("--schema", default="libra")
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--load-id", default=f"libra-{uuid.uuid4().hex[:16]}")
    args = command.parse_args(argv)
    client = DatabricksCli(args.databricks, args.profile, args.warehouse_id)
    manifest = build_package(client, args.catalog, args.schema, args.output, args.load_id)
    print(f"Wrote governed manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
