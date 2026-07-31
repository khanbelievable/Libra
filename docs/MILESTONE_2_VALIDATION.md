# Milestone 2 Validation

Validation date: 2026-08-01

Snowflake execution base commit: `4b1e686718b16a40d835cb6474ce3e661df7b808`

Implementation state: authenticated Snowflake acceptance complete; Power BI Desktop runtime and
visual review remain a manual gate.

This record deliberately omits account and workspace URLs, user identities, credentials, tokens,
connection files, MFA details, query identifiers, and raw authentication payloads. Generated
governed source packages remain ignored and untracked.

## Gate status

| Gate | Status | Evidence |
|---|---|---|
| Repository preflight | PASS | clean `main` at the execution base; three reviewed Milestone 2 commits ahead of `origin/main` |
| Snowflake connection | PASS | Snowflake CLI 3.23.0; named connection returned `Status OK`; deployment role `ACCOUNTADMIN`; existing warehouse `COMPUTE_WH` |
| Governed Databricks export | PASS | previously authenticated ten-table package revalidated from its manifest, checksums, row counts, and totals |
| Snowflake bootstrap | PASS | four roles, `LIBRA` database, four schemas, and migration ledger created |
| Ordered migrations | PASS | checksum-aware migrations `001` through `004` compiled and applied in order |
| Snowflake object inventory | PASS | 4 control tables, 10 staging tables, 11 core tables, 19 reporting views, 1 procedure, 1 stage, and 1 file format |
| First governed load | PASS | package returned `LOADED`; publication procedure returned success |
| Unchanged second load | PASS | same package returned `UNCHANGED`; one successful load run and zero failed runs retained |
| Reconciliation | PASS | all 15 blocking controls passed with exact `0.00` differences |
| Live grants | PASS | loader has no reporting grant; readers have only approved reporting views and no write/owner grants |
| Snowflake schema contract | PASS | fixed-scale monetary/rate columns; zero duplicate invoice, cost, or shipment keys |
| Power BI project source | PASS | connected authoring validation reported zero errors/warnings; restricted-network recheck reported zero errors and seven schema-fetch warnings |
| Power BI Desktop refresh/DAX/render | NOT RUN | Desktop execution and visual inspection remain manual; no runtime result is claimed |

Milestone 3 must not begin until the remaining Power BI Desktop gate is returned as evidence.

## Live Snowflake deployment

The authenticated bootstrap created the four intended roles: `LIBRA_OWNER`, `LIBRA_LOADER`,
`LIBRA_FINANCE_READER`, and `LIBRA_DQ_READER`. It created the `LIBRA` database with `CONTROL`,
`LOAD`, `CORE`, and `REPORTING` schemas. The existing `COMPUTE_WH` warehouse was reused; no
warehouse was created.

| Object class | Live count |
|---|---:|
| Applied migration-history rows | 4 |
| Control/audit tables | 4 |
| Load/staging tables | 10 |
| Core dimensions and facts | 11 |
| Reporting views | 19 |
| Publication procedures | 1 |
| Internal stages | 1 |
| Governed CSV file formats | 1 |

Core comprises six dimensions and five facts. Control includes migration history, load run/item,
and persisted reconciliation results. The stage, CSV format, and owner-executed publication
procedure are live and were exercised by the accepted load.

## Governed package and idempotency

The ignored package `snowflake/packages/m2-approved-v2` was originally generated through the
authenticated Databricks SQL export workflow from approved `workspace.libra` Silver and quality
tables. Before Snowflake loading it was revalidated locally as contract version `1.0`, load
`m2-correction-aware-v2`, with all ten required tables. Its source fingerprint is
`3db90a420655b78b06a14af6a257469c386116e663756379416ca76ad74fca1e`.

The first Snowflake execution returned `LOADED`. Repeating the unchanged package returned
`UNCHANGED` before staging or publication. Live audit state contains one `SUCCEEDED` load run and
zero `FAILED` runs for the load ID.

| Source table | Source rows | Target rows | Row difference | Source EUR | Target EUR | Financial difference |
|---|---:|---:|---:|---:|---:|---:|
| countries | 5 | 5 | 0 | - | - | - |
| currencies | 3 | 3 | 0 | - | - | - |
| customers | 20 | 20 | 0 | - | - | - |
| cost centers | 10 | 10 | 0 | - | - | - |
| routes | 10 | 10 | 0 | - | - | - |
| shipments | 720 | 720 | 0 | 916,353.44 | 916,353.44 | 0.00 |
| invoices | 720 | 720 | 0 | 916,351.47 | 916,351.47 | 0.00 |
| operational costs | 2,880 | 2,880 | 0 | 230,279.65 | 230,279.65 | 0.00 |
| budgets | 120 | 120 | 0 | 3,048,056.60 | 3,048,056.60 | 0.00 |
| data-quality results | 76 | 76 | 0 | - | - | - |

Shipment revenue remains an operational comparison. Invoice revenue is the recognized financial
source. Every governed Databricks-to-Snowflake financial difference is exactly zero.

## Live reconciliation

| Control | Expected | Snowflake | Difference |
|---|---:|---:|---:|
| Invoices | 720 | 720 | 0.00 |
| Operational costs | 2,880 | 2,880 | 0.00 |
| Revenue EUR | 916,351.47 | 916,351.47 | 0.00 |
| Operational cost EUR | 230,279.65 | 230,279.65 | 0.00 |
| Gross profit EUR | 686,071.82 | 686,071.82 | 0.00 |
| Budget EUR | 3,048,056.60 | 3,048,056.60 | 0.00 |
| Monthly country finance | 60 | 60 | 0.00 |
| Route profitability | 120 | 120 | 0.00 |
| Customer profitability | 240 | 240 | 0.00 |
| Budget versus actual | 120 | 120 | 0.00 |
| Healthy DQ snapshot | 38 | 38 | 0.00 |
| Retained correction-aware DQ | 76 | 76 | 0.00 |
| Duplicate invoice IDs | 0 | 0 | 0.00 |
| Duplicate cost IDs | 0 | 0 | 0.00 |
| Duplicate shipment IDs | 0 | 0 | 0.00 |

All monetary columns inspected in `CORE` are `NUMBER(20,2)` and all FX rate columns are
`NUMBER(18,6)`.

## Live role controls

Environment-specific `USAGE` was granted on the existing `COMPUTE_WH` warehouse to all four
LIBRA roles.

| Role | Live result |
|---|---|
| `LIBRA_LOADER` | 0 reporting grants; CONTROL/LOAD tables, package stage, publication procedure, database/schema usage, and warehouse usage only |
| `LIBRA_FINANCE_READER` | 15 approved reporting-view `SELECT` grants; 0 CONTROL/LOAD/CORE object grants; 0 write or owner grants |
| `LIBRA_DQ_READER` | 4 approved reporting-view `SELECT` grants; 0 CONTROL/LOAD/CORE object grants; 0 write or owner grants |

No Power BI identity was assigned owner or loader privileges. Assigning the two reader roles to a
future Power BI service identity remains an environment-owner action.

## Repository quality

| Gate | Result |
|---|---|
| Full pytest suite | 180 passed |
| Branch coverage | 95.35% |
| Ruff lint | PASS |
| Ruff format check | PASS |
| Strict mypy | PASS |
| pip check | PASS |
| Wheel build/install/CLI smoke outside checkout | PASS |
| Microsoft PBIR validation | PASS; 0 errors; prior connected run 0 warnings; restricted-network recheck 7 schema-fetch warnings |
| Authenticated Snowflake deployment/load/reconciliation | PASS |

## Remaining Power BI Desktop gate

Open `powerbi/Libra/Libra.pbip` in a current Power BI Desktop build, set the
`SnowflakeServer` and `SnowflakeWarehouse` parameters, authenticate with only the finance and DQ
reader roles, refresh, and validate the four finance totals. Then confirm the 22 active
single-direction relationships, 14 measures, seven pages, slicer interactions, route/customer
filtering, DQ history, refresh status, and transaction drill-through. Inspect every page at
**Fit to page** and capture one screenshot per page under `docs/evidence/milestone-2/`.

Until that is performed, this repository makes no claim that Power BI Desktop refreshed, DAX
executed, interactions worked, or visuals rendered correctly.
