# Milestone 2 Validation

Validation date: 2026-07-30

Starting repository commit: `e71f68c017d46dfcc83a53013de4dea7289a51c7`

Implementation state: local source complete; external Snowflake and Power BI runtime gates blocked.

This record omits private workspace/account URLs, identities, credentials, tokens, connection
files, and raw authentication payloads.

## Gate status

| Gate | Status | Evidence |
|---|---|---|
| Repository preflight and origin sync | PASS | clean `main`; start commit matched `origin/main` |
| Snowflake environment discovery | BLOCKED | no CLI, SnowSQL, named connector connection, or standard environment configuration found |
| Databricks governed export | PASS | existing authenticated `LIBRA` profile and SQL warehouse; ten-table package validated |
| Snowflake migrations and SQL contracts | PASS locally | ordered/checksummed migrations and 23 focused tests |
| Snowflake deployment and object creation | NOT RUN | no authenticated Snowflake account context |
| Snowflake load/reconciliation/grants | NOT RUN | depends on deployment; no values are claimed |
| Power BI project creation | PASS | real PBIP/TMDL/PBIR project under `powerbi/Libra` |
| PBIR schema validation | PASS | Microsoft authoring CLI 0.1.4; zero errors, zero warnings |
| Power BI refresh/DAX/render | NOT RUN | Power BI Desktop is not installed and Snowflake is not deployed |
| Visual interaction/screenshots | NOT RUN | requires refreshed Desktop session |

Milestone 2 is not complete and Milestone 3 may not begin.

## Repository quality

| Gate | Result |
|---|---|
| Full pytest suite | 180 passed |
| Branch coverage | 95.87% after focused final-hardening coverage append |
| Ruff lint | PASS |
| Ruff format check | PASS |
| Strict mypy | PASS |
| pip check | PASS |
| Wheel build/install/CLI smoke outside checkout | PASS |
| Microsoft PBIR validation | PASS; 0 errors, 0 warnings |
| Authenticated Snowflake smoke | SKIPPED; named connection unavailable |

## Implemented Snowflake source

- Database contract: `LIBRA`
- Schemas: `CONTROL`, `LOAD`, `CORE`, `REPORTING`
- Roles: `LIBRA_OWNER`, `LIBRA_LOADER`, `LIBRA_FINANCE_READER`, `LIBRA_DQ_READER`
- Migrations: `001` through `004`
- Core objects: 6 dimensions, 5 facts
- Reporting objects: 19 stable views
- Audit objects: migration history, load run/item, reconciliation result
- Load boundary: internal stage, header-aware CSV format, manifest/checksum validation,
  load-specific stage paths, natural-key MERGE, fingerprint no-op

SQLGlot 30.14.0 parses every standard migration statement in Snowflake dialect. The Snowflake
connector available for an eventual authenticated run is 4.7.1. Stored-procedure execution is
covered by structural contracts and fake-connector transaction tests; it has not been compiled in
Snowflake.

## Governed Databricks export

The ignored package `snowflake/packages/m2-approved-v2` was generated from approved
`workspace.libra` Silver/quality tables through the existing authenticated Databricks SQL
warehouse. The package fingerprint is
`3db90a420655b78b06a14af6a257469c386116e663756379416ca76ad74fca1e`.

| Source table | Rows | EUR total |
|---|---:|---:|
| countries | 5 | — |
| currencies | 3 | — |
| customers | 20 | — |
| cost_centers | 10 | — |
| routes | 10 | — |
| shipments | 720 | 916,353.44 |
| invoices | 720 | 916,351.47 |
| operational_costs | 2,880 | 230,279.65 |
| budgets | 120 | 3,048,056.60 |
| data_quality_results | 76 | — |

Shipment revenue is retained only as an operational comparison. Invoice revenue remains the
recognized financial source. The 76 quality rows are the correction-aware retained history:
38 healthy snapshot controls plus 38 correction-owner controls.

## Implemented Power BI source

| Contract | Count |
|---|---:|
| Model tables | 12 |
| Relationships | 22 |
| Approved measures | 14 |
| Report pages | 7 |
| Data-bound visuals | 30 |

All relationships are one-direction from dimensions to facts; there are no fact-to-fact or
bidirectional paths. Direct shipment-derived route/customer keys let filters reproduce the
approved direct allocation without shared-cost logic. The seven pages include KPI cards,
month/country analyses, cost/budget/quality tables or charts, date and country slicers, and a
governed invoice drill-through page.

PBIR source validation succeeded. TMDL compilation, source refresh, DAX result evaluation, broken
visual checks, slicer interactions, drill-through behavior, formatting review, and screenshots
remain unverified and are not presented as complete.

## Manual continuation

Create a named Snowflake connector connection called `libra` in the standard local
`connections.toml`, using an existing approved warehouse and a role allowed to run the bootstrap.
Then execute the commands in `snowflake/README.md` and return the sanitized reconciliation/grant
results. After those pass, install/open Power BI Desktop and follow `powerbi/README.md`.
