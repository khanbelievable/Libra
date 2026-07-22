# Acceptance Criteria

## Slice 001

- Installation succeeds on Python 3.12 with the documented commands.
- Equal seed/scenario inputs produce byte-identical CSV files and manifests.
- Healthy data covers every month of 2025, five countries, and EUR/GBP/TRY.
- Healthy processing has no quarantined rows and all critical quality rules pass.
- Duplicate invoice occurrences are quarantined and cannot inflate Silver revenue.
- Exact invoice redelivery under another active batch remains owned once; conflicting
  canonical payloads withhold every occurrence until the owning batch is corrected.
- Reprocessing or correcting one batch cannot remove unrelated rows owned by another batch.
- GBP facts without a same-date GBP/EUR rate are quarantined with `MISSING_EXCHANGE_RATE` and no EUR amount.
- Zero, negative, malformed, missing, non-finite, duplicate, or conflicting FX values cannot
  produce a trusted EUR amount.
- Monetary values in trusted output are finite, valid decimals and non-negative where required.
- A Germany invoice delivery approximately 70% below baseline fails `INVOICE_COUNTRY_VOLUME` and its delivered Germany rows do not enter Silver.
- Unknown country, currency, customer, cost-center, and shipment references are quarantined
  with precise reason codes.
- Silver dates/codes/identifiers/decimals conform to documented contracts.
- Source dates use `YYYY-MM-DD`; decimals use a dot separator without grouping characters.
- Bronze, Silver, quarantine, quality result, reconciliation, and versioned state evidence is persisted.
- Reconciliation reads committed storage and detects missing rows, changed amounts, business-key
  differences, and omitted batch contributions.
- Re-running an unchanged batch is a no-op only when fingerprint, pipeline version, data-contract
  version, rules fingerprint, and prior summary are compatible.
- A changed payload under the same batch ID retains both Bronze versions and replaces its prior Silver contribution before upsert.
- Unit, integration, contract, and demo test suites pass without Databricks or Snowflake credentials.
- The wheel includes runtime defaults and the installed CLI runs outside a repository checkout.
- Steward-facing Silver, quarantine, claims, and quality CSVs neutralize spreadsheet-formula prefixes;
  immutable Bronze retains the exact source value.
- Snowflake and Power BI contain only reviewed interfaces/specifications; no fake deployment or PBIX is claimed.

## Evidence

Automated acceptance evidence is in `tests/demo`. Human-readable values and commands are in `demo/expected-results/SLICE_001.md`. The completed implementation review is recorded in `docs/SLICE_001_REVIEW.md`.
