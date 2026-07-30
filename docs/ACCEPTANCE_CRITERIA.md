# Acceptance Criteria

## Slice 001

- Installation succeeds on Python 3.12 with the documented commands.
- Equal seed/scenario inputs produce byte-identical CSV files and manifests.
- Healthy data covers every month of 2025, five countries, and EUR/GBP/TRY.
- Healthy processing has no quarantined rows and all critical quality rules pass.
- Duplicate invoice occurrences are quarantined and cannot inflate Silver revenue.
- Exact invoice redelivery under another active batch remains owned once; conflicting
  canonical payloads withhold every occurrence until the owning batch is corrected.
- Ownership is ranked only by persisted immutable arrival sequence and cannot change when JSON
  keys are sorted or an unrelated batch arrives.
- A changed applied FX basis or translated EUR result is a conflicting financial claim.
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
  version, rules fingerprint, claim attestations, Silver, quarantine, quality, reconciliation,
  and summary evidence are compatible.
- A changed payload under the same batch ID retains both Bronze versions and replaces its prior Silver contribution before upsert.
- Unit, integration, contract, and demo test suites pass without Databricks or Snowflake credentials.
- The wheel includes runtime defaults and the installed CLI runs outside a repository checkout.
- Internal CSV persistence preserves canonical identifiers. Formula neutralization occurs only at
  an explicit spreadsheet export boundary.
- Missing, truncated, duplicated, altered, mis-owned, or stale claim evidence cannot shrink
  trusted Silver or advance processed state.
- Exact shipment/budget replays retain the first owner; conflicting cross-batch monetary facts
  fail closed unless a generated correction manifest explicitly declares the owner it supersedes.
- Snowflake and Power BI contain only reviewed interfaces/specifications; no fake deployment or PBIX is claimed.

## Evidence

Automated acceptance evidence is in `tests/demo`. Human-readable values and commands are in `demo/expected-results/SLICE_001.md`. The completed implementation review is recorded in `docs/SLICE_001_REVIEW.md`.

## Milestone 1

- Every shipment has a valid route and finite positive volume.
- Healthy data contains exactly four operational-cost categories and trusted costs reconcile in EUR.
- Invalid cost amount, type, currency, FX, country, route, shipment, or cost center is quarantined.
- Monthly country, route, customer, budget-versus-actual, and data-quality Gold contracts have
  explicit deterministic schemas and reconcile to Silver.
- Direct shipment allocation satisfies `revenue - allocated cost = gross profit`.
- The correction demonstration changes January 2025 history without duplicate invoice or cost IDs
  and preserves batch arrival sequence.
- Local PySpark contracts use DecimalType and reproduce local financial controls.
- The Databricks bundle contains one three-task job and no credentials.
- Cloud validation, deployment, job execution, Delta inspection, and local/cloud comparison are
  reported independently; unavailable authentication is never presented as a successful run.

## Milestone 2

- Ordered Snowflake bootstrap/migrations define `LIBRA` with `CONTROL`, `LOAD`, `CORE`, and
  `REPORTING` schemas, six dimensions, five facts, stable reporting views, load audit, and
  reconciliation controls.
- The governed Databricks export is deterministic, contract-versioned, checksummed, and excludes
  credentials and workspace identity.
- A successful source fingerprint is an unchanged no-op; changed packages publish through
  natural-key MERGE statements and finance differences prevent a successful commit.
- Money and rate columns use fixed-scale `NUMBER`; invoice revenue remains the recognized source.
- Reader roles can select only their approved reporting views. The loader receives no reporting
  reader grant and Power BI receives no owner/loader privilege.
- The real Power BI project contains 12 model tables, single-direction dimension relationships,
  14 approved DAX measures, seven data-bound pages, date/country slicers, and governed
  drill-through fields.
- Credential-free SQL, package, migration, load, semantic-model, and PBIR contracts run in CI.
- Authenticated deployment/load, zero-difference Snowflake controls, Power BI refresh/DAX
  execution, interaction checks, and visual review are separate blocking evidence gates.
