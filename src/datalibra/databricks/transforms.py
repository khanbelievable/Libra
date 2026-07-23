"""PySpark standardization, validation, FX conversion, and Gold transforms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from datalibra.domain.contracts import COST_TYPES
from datalibra.quality.rules import REASON_TO_RULE, RULE_DATASETS

MONEY_TYPE = "decimal(20,2)"
RATE_TYPE = "decimal(18,6)"
PERCENT_TYPE = "decimal(18,4)"


def _identifier(column: Any) -> Any:
    from pyspark.sql import functions as F

    return F.upper(F.regexp_replace(F.trim(column), " ", "-"))


def _code(column: Any) -> Any:
    from pyspark.sql import functions as F

    return F.upper(F.trim(column))


def _try_cast(column_name: str, type_name: str) -> Any:
    from pyspark.sql import functions as F

    return F.expr(f"try_cast({column_name} as {type_name})")


def _reason_array(items: Sequence[tuple[Any, str]]) -> Any:
    from pyspark.sql import functions as F

    return F.filter(
        F.array(*(F.when(condition, F.lit(reason)) for condition, reason in items)),
        lambda value: value.isNotNull(),
    )


def _split_by_reasons(frame: Any, reasons: Any, *, drop: Sequence[str] = ()) -> tuple[Any, Any]:
    from pyspark.sql import functions as F

    marked = frame.withColumn("_reason_array", reasons)
    trusted = marked.filter(F.size("_reason_array") == 0).drop("_reason_array", *drop)
    quarantine = (
        marked.filter(F.size("_reason_array") > 0)
        .withColumn("_reason_codes", F.concat_ws("|", F.array_sort("_reason_array")))
        .drop("_reason_array", *drop)
    )
    return trusted, quarantine


def _fx_rates(rates: Any) -> Any:
    from pyspark.sql import functions as F

    return rates.select(
        F.col("rate_date").alias("_fx_date"),
        F.col("currency_code").alias("_fx_currency"),
        F.col("rate_to_eur").alias("_fx_rate"),
    )


def standardize_batch(frames: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Transform one Bronze batch into typed trusted and quarantine DataFrames."""

    from pyspark.sql import Window
    from pyspark.sql import functions as F

    trusted: dict[str, Any] = {}
    quarantine: dict[str, Any] = {}

    countries = (
        frames["countries"]
        .withColumn("country_code", _code(F.col("country_code")))
        .withColumn("default_currency", _code(F.col("default_currency")))
    )
    currencies = (
        frames["currencies"]
        .withColumn("currency_code", _code(F.col("currency_code")))
        .withColumn("decimal_places", _try_cast("decimal_places", "int"))
    )
    trusted["countries"], quarantine["countries"] = countries, countries.limit(0)
    trusted["currencies"], quarantine["currencies"] = currencies, currencies.limit(0)

    country_refs = countries.select(F.col("country_code").alias("_valid_country")).distinct()
    currency_refs = currencies.select(F.col("currency_code").alias("_valid_currency")).distinct()

    customers = (
        frames["customers"]
        .withColumn("customer_id", _identifier(F.col("customer_id")))
        .withColumn("country_code", _code(F.col("country_code")))
        .join(
            country_refs,
            F.col("country_code") == F.col("_valid_country"),
            "left",
        )
    )
    trusted["customers"], quarantine["customers"] = _split_by_reasons(
        customers,
        _reason_array([(F.col("_valid_country").isNull(), "UNKNOWN_COUNTRY_CODE")]),
        drop=("_valid_country",),
    )

    cost_centers = (
        frames["cost_centers"]
        .withColumn("cost_center_id", _identifier(F.col("cost_center_id")))
        .withColumn("country_code", _code(F.col("country_code")))
        .join(
            country_refs,
            F.col("country_code") == F.col("_valid_country"),
            "left",
        )
    )
    trusted["cost_centers"], quarantine["cost_centers"] = _split_by_reasons(
        cost_centers,
        _reason_array([(F.col("_valid_country").isNull(), "UNKNOWN_COUNTRY_CODE")]),
        drop=("_valid_country",),
    )

    rates = (
        frames["exchange_rates"]
        .withColumn("rate_date", F.to_date("rate_date"))
        .withColumn("currency_code", _code(F.col("currency_code")))
        .withColumn("rate_to_eur", _try_cast("rate_to_eur", RATE_TYPE))
        .join(
            currency_refs,
            F.col("currency_code") == F.col("_valid_currency"),
            "left",
        )
    )
    trusted["exchange_rates"], quarantine["exchange_rates"] = _split_by_reasons(
        rates,
        _reason_array(
            [
                (
                    F.col("rate_date").isNull()
                    | F.col("rate_to_eur").isNull()
                    | (F.col("rate_to_eur") <= 0),
                    "INVALID_EXCHANGE_RATE",
                ),
                (F.col("_valid_currency").isNull(), "UNKNOWN_CURRENCY_CODE"),
            ]
        ),
        drop=("_valid_currency",),
    )

    routes = (
        frames["routes"]
        .withColumn("route_id", _identifier(F.col("route_id")))
        .withColumn("origin_country_code", _code(F.col("origin_country_code")))
        .withColumn("destination_country_code", _code(F.col("destination_country_code")))
        .withColumn("transport_mode", _code(F.col("transport_mode")))
        .withColumn("distance_km", _try_cast("distance_km", MONEY_TYPE))
        .withColumn("standard_transit_days", _try_cast("standard_transit_days", "int"))
        .join(
            country_refs.select(F.col("_valid_country").alias("_valid_origin")),
            F.col("origin_country_code") == F.col("_valid_origin"),
            "left",
        )
        .join(
            country_refs.select(F.col("_valid_country").alias("_valid_destination")),
            F.col("destination_country_code") == F.col("_valid_destination"),
            "left",
        )
    )
    trusted["routes"], quarantine["routes"] = _split_by_reasons(
        routes,
        _reason_array(
            [
                (
                    F.col("route_id").isNull()
                    | F.col("distance_km").isNull()
                    | (F.col("distance_km") <= 0)
                    | F.col("standard_transit_days").isNull()
                    | (F.col("standard_transit_days") <= 0),
                    "INVALID_ROUTE_DEFINITION",
                ),
                (
                    F.col("_valid_origin").isNull() | F.col("_valid_destination").isNull(),
                    "UNKNOWN_COUNTRY_CODE",
                ),
            ]
        ),
        drop=("_valid_origin", "_valid_destination"),
    )

    customer_refs = trusted["customers"].select(F.col("customer_id").alias("_valid_customer"))
    cost_center_refs = trusted["cost_centers"].select(
        F.col("cost_center_id").alias("_valid_cost_center")
    )
    route_refs = trusted["routes"].select(F.col("route_id").alias("_valid_route"))
    valid_rates = _fx_rates(trusted["exchange_rates"])

    shipments = (
        frames["shipments"]
        .withColumn("shipment_id", _identifier(F.col("shipment_id")))
        .withColumn("shipment_date", F.to_date("shipment_date"))
        .withColumn("route_id", _identifier(F.col("route_id")))
        .withColumn("volume_m3", _try_cast("volume_m3", MONEY_TYPE))
        .withColumn("country_code", _code(F.col("country_code")))
        .withColumn("customer_id", _identifier(F.col("customer_id")))
        .withColumn("cost_center_id", _identifier(F.col("cost_center_id")))
        .withColumn("currency_code", _code(F.col("currency_code")))
        .withColumn("revenue_amount", _try_cast("revenue_amount", MONEY_TYPE))
        .join(route_refs, F.col("route_id") == F.col("_valid_route"), "left")
        .join(customer_refs, F.col("customer_id") == F.col("_valid_customer"), "left")
        .join(
            cost_center_refs,
            F.col("cost_center_id") == F.col("_valid_cost_center"),
            "left",
        )
        .join(country_refs, F.col("country_code") == F.col("_valid_country"), "left")
        .join(currency_refs, F.col("currency_code") == F.col("_valid_currency"), "left")
        .join(
            valid_rates,
            (F.col("shipment_date") == F.col("_fx_date"))
            & (F.col("currency_code") == F.col("_fx_currency")),
            "left",
        )
        .withColumn("fx_rate_to_eur", F.col("_fx_rate").cast(RATE_TYPE))
        .withColumn(
            "amount_eur",
            (F.col("revenue_amount") * F.col("_fx_rate")).cast(MONEY_TYPE),
        )
    )
    fact_markers = (
        "_valid_route",
        "_valid_customer",
        "_valid_cost_center",
        "_valid_country",
        "_valid_currency",
        "_fx_date",
        "_fx_currency",
        "_fx_rate",
    )
    trusted["shipments"], quarantine["shipments"] = _split_by_reasons(
        shipments,
        _reason_array(
            [
                (
                    F.col("shipment_id").isNull()
                    | F.col("customer_id").isNull()
                    | F.col("cost_center_id").isNull()
                    | F.col("route_id").isNull(),
                    "REQUIRED_IDENTIFIERS",
                ),
                (
                    F.col("revenue_amount").isNull() | (F.col("revenue_amount") < 0),
                    "INVALID_FINANCIAL_VALUE",
                ),
                (
                    F.col("volume_m3").isNull() | (F.col("volume_m3") <= 0),
                    "INVALID_SHIPMENT_VOLUME",
                ),
                (F.col("_valid_route").isNull(), "UNKNOWN_ROUTE_ID"),
                (F.col("_valid_customer").isNull(), "UNKNOWN_CUSTOMER_ID"),
                (F.col("_valid_cost_center").isNull(), "UNKNOWN_COST_CENTER_ID"),
                (F.col("_valid_country").isNull(), "UNKNOWN_COUNTRY_CODE"),
                (F.col("_valid_currency").isNull(), "UNKNOWN_CURRENCY_CODE"),
                (
                    F.col("_valid_currency").isNotNull() & F.col("_fx_rate").isNull(),
                    "MISSING_EXCHANGE_RATE",
                ),
            ]
        ),
        drop=fact_markers,
    )

    shipment_refs = trusted["shipments"].select(F.col("shipment_id").alias("_valid_shipment"))
    invoices = (
        frames["invoices"]
        .withColumn("invoice_id", _identifier(F.col("invoice_id")))
        .withColumn("shipment_id", _identifier(F.col("shipment_id")))
        .withColumn("invoice_date", F.to_date("invoice_date"))
        .withColumn("country_code", _code(F.col("country_code")))
        .withColumn("customer_id", _identifier(F.col("customer_id")))
        .withColumn("cost_center_id", _identifier(F.col("cost_center_id")))
        .withColumn("currency_code", _code(F.col("currency_code")))
        .withColumn("revenue_amount", _try_cast("revenue_amount", MONEY_TYPE))
        .join(
            shipment_refs,
            F.col("shipment_id") == F.col("_valid_shipment"),
            "left",
        )
        .join(customer_refs, F.col("customer_id") == F.col("_valid_customer"), "left")
        .join(
            cost_center_refs,
            F.col("cost_center_id") == F.col("_valid_cost_center"),
            "left",
        )
        .join(country_refs, F.col("country_code") == F.col("_valid_country"), "left")
        .join(currency_refs, F.col("currency_code") == F.col("_valid_currency"), "left")
        .join(
            valid_rates,
            (F.col("invoice_date") == F.col("_fx_date"))
            & (F.col("currency_code") == F.col("_fx_currency")),
            "left",
        )
        .withColumn("fx_rate_to_eur", F.col("_fx_rate").cast(RATE_TYPE))
        .withColumn(
            "amount_eur",
            (F.col("revenue_amount") * F.col("_fx_rate")).cast(MONEY_TYPE),
        )
    )
    invoice_window = Window.partitionBy("invoice_id").orderBy("_source_row_number")
    invoice_counts = invoices.groupBy("invoice_id").agg(
        F.count("*").alias("_invoice_count"),
        F.countDistinct(
            F.sha2(
                F.concat_ws(
                    "|",
                    "shipment_id",
                    F.col("invoice_date").cast("string"),
                    "country_code",
                    "customer_id",
                    "cost_center_id",
                    "currency_code",
                    F.col("revenue_amount").cast("string"),
                    F.col("fx_rate_to_eur").cast("string"),
                    F.col("amount_eur").cast("string"),
                ),
                256,
            )
        ).alias("_claim_count"),
    )
    invoices = invoices.join(invoice_counts, "invoice_id", "left").withColumn(
        "_invoice_row", F.row_number().over(invoice_window)
    )
    invoice_markers = (
        "_valid_shipment",
        "_valid_customer",
        "_valid_cost_center",
        "_valid_country",
        "_valid_currency",
        "_fx_date",
        "_fx_currency",
        "_fx_rate",
        "_invoice_count",
        "_claim_count",
        "_invoice_row",
    )
    trusted["invoices"], quarantine["invoices"] = _split_by_reasons(
        invoices,
        _reason_array(
            [
                (
                    F.col("invoice_id").isNull()
                    | F.col("shipment_id").isNull()
                    | F.col("customer_id").isNull()
                    | F.col("cost_center_id").isNull(),
                    "REQUIRED_IDENTIFIERS",
                ),
                (
                    F.col("revenue_amount").isNull() | (F.col("revenue_amount") < 0),
                    "INVALID_FINANCIAL_VALUE",
                ),
                (F.col("_valid_shipment").isNull(), "UNKNOWN_SHIPMENT_ID"),
                (F.col("_valid_customer").isNull(), "UNKNOWN_CUSTOMER_ID"),
                (F.col("_valid_cost_center").isNull(), "UNKNOWN_COST_CENTER_ID"),
                (F.col("_valid_country").isNull(), "UNKNOWN_COUNTRY_CODE"),
                (F.col("_valid_currency").isNull(), "UNKNOWN_CURRENCY_CODE"),
                (
                    F.col("_valid_currency").isNotNull() & F.col("_fx_rate").isNull(),
                    "MISSING_EXCHANGE_RATE",
                ),
                (F.col("_claim_count") > 1, "CONFLICTING_DUPLICATE_INVOICE"),
                (
                    (F.col("_claim_count") == 1) & (F.col("_invoice_row") > 1),
                    "DUPLICATE_INVOICE",
                ),
            ]
        ),
        drop=invoice_markers,
    )

    budgets = (
        frames["budgets"]
        .withColumn("month_start", F.to_date("month_start"))
        .withColumn("cost_center_id", _identifier(F.col("cost_center_id")))
        .withColumn("currency_code", _code(F.col("currency_code")))
        .withColumn("budget_amount", _try_cast("budget_amount", MONEY_TYPE))
        .join(
            cost_center_refs,
            F.col("cost_center_id") == F.col("_valid_cost_center"),
            "left",
        )
        .join(currency_refs, F.col("currency_code") == F.col("_valid_currency"), "left")
        .join(
            valid_rates,
            (F.col("month_start") == F.col("_fx_date"))
            & (F.col("currency_code") == F.col("_fx_currency")),
            "left",
        )
        .withColumn("fx_rate_to_eur", F.col("_fx_rate").cast(RATE_TYPE))
        .withColumn(
            "amount_eur",
            (F.col("budget_amount") * F.col("_fx_rate")).cast(MONEY_TYPE),
        )
    )
    trusted["budgets"], quarantine["budgets"] = _split_by_reasons(
        budgets,
        _reason_array(
            [
                (F.col("cost_center_id").isNull(), "REQUIRED_IDENTIFIERS"),
                (
                    F.col("budget_amount").isNull() | (F.col("budget_amount") < 0),
                    "INVALID_FINANCIAL_VALUE",
                ),
                (F.col("_valid_cost_center").isNull(), "UNKNOWN_COST_CENTER_ID"),
                (F.col("_valid_currency").isNull(), "UNKNOWN_CURRENCY_CODE"),
                (
                    F.col("_valid_currency").isNotNull() & F.col("_fx_rate").isNull(),
                    "MISSING_EXCHANGE_RATE",
                ),
            ]
        ),
        drop=(
            "_valid_cost_center",
            "_valid_currency",
            "_fx_date",
            "_fx_currency",
            "_fx_rate",
        ),
    )

    operational_costs = (
        frames["operational_costs"]
        .withColumn("cost_id", _identifier(F.col("cost_id")))
        .withColumn("shipment_id", _identifier(F.col("shipment_id")))
        .withColumn("route_id", _identifier(F.col("route_id")))
        .withColumn("cost_center_id", _identifier(F.col("cost_center_id")))
        .withColumn("country_code", _code(F.col("country_code")))
        .withColumn("posting_date", F.to_date("posting_date"))
        .withColumn("cost_type", _code(F.col("cost_type")))
        .withColumn("amount", _try_cast("amount", MONEY_TYPE))
        .withColumn("currency_code", _code(F.col("currency_code")))
        .join(
            shipment_refs,
            F.col("shipment_id") == F.col("_valid_shipment"),
            "left",
        )
        .join(route_refs, F.col("route_id") == F.col("_valid_route"), "left")
        .join(
            cost_center_refs,
            F.col("cost_center_id") == F.col("_valid_cost_center"),
            "left",
        )
        .join(country_refs, F.col("country_code") == F.col("_valid_country"), "left")
        .join(currency_refs, F.col("currency_code") == F.col("_valid_currency"), "left")
        .join(
            valid_rates,
            (F.col("posting_date") == F.col("_fx_date"))
            & (F.col("currency_code") == F.col("_fx_currency")),
            "left",
        )
        .withColumn("fx_rate_to_eur", F.col("_fx_rate").cast(RATE_TYPE))
        .withColumn("amount_eur", (F.col("amount") * F.col("_fx_rate")).cast(MONEY_TYPE))
    )
    cost_markers = (
        "_valid_shipment",
        "_valid_route",
        "_valid_cost_center",
        "_valid_country",
        "_valid_currency",
        "_fx_date",
        "_fx_currency",
        "_fx_rate",
    )
    trusted["operational_costs"], quarantine["operational_costs"] = _split_by_reasons(
        operational_costs,
        _reason_array(
            [
                (
                    F.col("cost_id").isNull()
                    | F.col("shipment_id").isNull()
                    | F.col("route_id").isNull()
                    | F.col("cost_center_id").isNull(),
                    "REQUIRED_IDENTIFIERS",
                ),
                (
                    F.col("amount").isNull() | (F.col("amount") < 0),
                    "INVALID_FINANCIAL_VALUE",
                ),
                (~F.col("cost_type").isin(*COST_TYPES), "INVALID_COST_TYPE"),
                (F.col("_valid_shipment").isNull(), "UNKNOWN_SHIPMENT_ID"),
                (F.col("_valid_route").isNull(), "UNKNOWN_ROUTE_ID"),
                (F.col("_valid_cost_center").isNull(), "UNKNOWN_COST_CENTER_ID"),
                (F.col("_valid_country").isNull(), "UNKNOWN_COUNTRY_CODE"),
                (F.col("_valid_currency").isNull(), "UNKNOWN_CURRENCY_CODE"),
                (
                    F.col("_valid_currency").isNotNull() & F.col("_fx_rate").isNull(),
                    "MISSING_EXCHANGE_RATE",
                ),
            ]
        ),
        drop=cost_markers,
    )
    return trusted, quarantine


def quality_results(quarantine: Mapping[str, Any], batch_id: str, timestamp: str) -> Any:
    """Create deterministic PASS/FAIL evidence from Spark quarantine outputs."""

    from pyspark.sql import functions as F

    frames = []
    for dataset, frame in quarantine.items():
        amount = (
            F.col("amount_eur") if "amount_eur" in frame.columns else F.lit(None).cast(MONEY_TYPE)
        )
        frames.append(
            frame.select(
                F.lit(dataset).alias("affected_dataset"),
                F.explode(F.split("_reason_codes", r"\|")).alias("failure_reason"),
                amount.alias("amount_eur"),
            )
        )
    exploded = frames[0]
    for frame in frames[1:]:
        exploded = exploded.unionByName(frame, allowMissingColumns=True)
    mapping_items = [
        item
        for reason, rule in sorted(REASON_TO_RULE.items())
        for item in (F.lit(reason), F.lit(rule))
    ]
    failures = (
        exploded.withColumn(
            "rule_name",
            F.create_map(*mapping_items)[F.col("failure_reason")],
        )
        .groupBy("affected_dataset", "rule_name")
        .agg(
            F.count("*").alias("failed_row_count"),
            F.sum("amount_eur").cast(MONEY_TYPE).alias("affected_financial_amount_eur"),
            F.concat_ws("|", F.array_sort(F.collect_set("failure_reason"))).alias("failure_reason"),
        )
    )
    spark = frames[0].sparkSession
    coverage = spark.createDataFrame(
        [
            (rule, dataset)
            for rule, datasets in sorted(RULE_DATASETS.items())
            for dataset in datasets
        ],
        "rule_name string, affected_dataset string",
    )
    return coverage.join(failures, ["rule_name", "affected_dataset"], "left").select(
        "rule_name",
        "affected_dataset",
        F.lit(batch_id).alias("batch_id"),
        F.lit(batch_id).alias("_batch_id"),
        F.coalesce("failure_reason", F.lit("")).alias("failure_reason"),
        F.coalesce("failed_row_count", F.lit(0)).alias("failed_row_count"),
        "affected_financial_amount_eur",
        F.to_timestamp(F.lit(timestamp)).alias("execution_timestamp"),
        F.when(F.col("failed_row_count").isNull(), F.lit("PASS"))
        .otherwise(F.lit("FAIL"))
        .alias("validation_status"),
    )
