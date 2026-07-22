# Acceptance Criteria

## Slice 001

- Installation succeeds on Python 3.12 with the documented commands.
- Equal seed/scenario inputs produce byte-identical CSV files and manifests.
- Healthy data covers every month of 2025, five countries, and EUR/GBP/TRY.
- Healthy processing has no quarantined rows and all critical quality rules pass.
- Duplicate invoice occurrences are quarantined and cannot inflate Silver revenue.
- GBP facts without a same-date GBP/EUR rate are quarantined with `MISSING_EXCHANGE_RATE` and no EUR amount.
- A Germany invoice delivery approximately 70% below baseline fails `INVOICE_COUNTRY_VOLUME` and its delivered Germany rows do not enter Silver.
- Missing and unknown customer/cost-center/shipment identifiers are detectable and quarantined.
- Silver dates/codes/identifiers/decimals conform to documented contracts.
- Bronze, Silver, quarantine, quality result, reconciliation, and state evidence is persisted.
- Re-running an unchanged batch is a no-op with identical Silver counts and totals.
- A changed payload under the same batch ID retains both Bronze versions and replaces its prior Silver contribution before upsert.
- Unit, integration, contract, and demo test suites pass without Databricks or Snowflake credentials.
- Snowflake and Power BI contain only reviewed interfaces/specifications; no fake deployment or PBIX is claimed.

## Evidence

Automated acceptance evidence is in `tests/demo`. Human-readable values and commands are in `demo/expected-results/SLICE_001.md`. The completed implementation review is recorded in `docs/SLICE_001_REVIEW.md`.
