# Milestone 1 Validation

Validation date: 2026-07-24

Validated implementation commit: `0c0e4a1`

Starting repository commit: `1d520c4de8c76718b52494fd8af69f4757ab1bdb`

Reference environment: Windows, Python 3.12.13, PySpark 4.1.3, Java 21,
Databricks CLI 1.9.0

This record intentionally omits the private workspace host, workspace user identity, OAuth
material, and raw API responses.

## Gate status

| Gate | Status | Evidence |
|---|---|---|
| Deterministic local Bronze/Silver/Gold | PASS | healthy, broken, and correction scenarios executed |
| Local PySpark contracts | PASS | explicit schemas, quarantine, fixed-scale decimals, and Gold parity |
| Python wheel | PASS | built, installed, and smoke-tested outside the checkout |
| Databricks authentication | PASS | profile `LIBRA`; auth description and current-user request succeeded |
| Authenticated bundle validation | PASS | bundle `libra-milestone-1`, target `dev`, no validation warnings |
| Bundle deployment | PASS | existing job updated; no duplicate job, schema, volume, or warehouse created |
| Healthy workspace execution | PASS | run `697800132890603`; all three tasks succeeded |
| Delta inspection | PASS | 37 tables inventoried; counts, finance schemas, quality, and controls queried |
| Local/cloud parity | PASS | all documented count and financial differences are zero |
| Historical correction | PASS | initial run `586763144261151`; corrected run `176675503042120` |

Milestone 1 is authenticated, deployed, workspace-executed, Delta-inspected, and correction
verified.

## Deployment evidence

The existing Unity Catalog schema and managed landing volume were discovered before deployment
and were not recreated or dropped. The existing serverless SQL warehouse was reused for
independent inspection.

The first real deployment exposed two serverless compatibility requirements:

- serverless wheel dependencies belong on the shared environment, not each task;
- the shared environment must use version `4` so its Python 3.12 runtime satisfies
  `datalibra`'s `>=3.12` requirement.

The deployed logical job is `dev-libra-milestone-1`, job ID `353937912877912`. It contains exactly:

```text
land_bronze -> build_silver -> build_gold_and_validate
```

The generated healthy manifest owns batch `slice001-healthy`. The job was run with that immutable
manifest identity; the manifest/parameter equality guard was not bypassed.

### Healthy run

| Item | Evidence |
|---|---|
| Run ID | `697800132890603` |
| Started | `2026-07-24T19:56:07Z` |
| Completed | `2026-07-24T20:01:25Z` |
| Duration | 318.4 seconds |
| Final state | `TERMINATED / SUCCESS` |

| Task | Task run ID | Result |
|---|---:|---|
| `land_bronze` | `103507518372185` | SUCCESS |
| `build_silver` | `810040045721995` | SUCCESS |
| `build_gold_and_validate` | `974717675443230` | SUCCESS |

The Bronze task verified source fingerprint
`1d8583e183a8ac7f96d87ebd1f06430725b224b93dcb48894398294647bde9f4`.

## Delta inspection

The healthy snapshot contained 37 Delta tables:

- Bronze: `bronze_budgets`, `bronze_cost_centers`, `bronze_countries`,
  `bronze_currencies`, `bronze_customers`, `bronze_exchange_rates`,
  `bronze_invoices`, `bronze_operational_costs`, `bronze_routes`,
  `bronze_shipments`
- Silver: the same ten dataset names prefixed with `silver_`
- Quarantine: the same ten dataset names prefixed with `quarantine_`
- Quality/audit: `quality_results`, `reconciliation_controls`
- Gold: `gold_monthly_country_finance`, `gold_route_profitability`,
  `gold_customer_profitability`, `gold_budget_vs_actual`,
  `gold_data_quality_summary`

### Healthy layer counts

| Dataset | Bronze | Silver | Quarantine |
|---|---:|---:|---:|
| budgets | 120 | 120 | 0 |
| cost centers | 10 | 10 | 0 |
| countries | 5 | 5 | 0 |
| currencies | 3 | 3 | 0 |
| customers | 20 | 20 | 0 |
| exchange rates | 1,095 | 1,095 | 0 |
| invoices | 720 | 720 | 0 |
| operational costs | 2,880 | 2,880 | 0 |
| routes | 10 | 10 | 0 |
| shipments | 720 | 720 | 0 |

`quality_results` contained 38 passing control rows. `reconciliation_controls` contained two
passing rows and no failure. No quarantine table contained a row.

### Finance schemas

Independent SQL inspection confirmed fixed-scale finance types:

- Silver invoice and operational-cost EUR amounts: `DECIMAL(20,2)`
- Silver source amounts: `DECIMAL(20,2)`
- Silver FX rates: `DECIMAL(18,6)`
- Gold revenue, cost, gross profit, and budget: `DECIMAL(20,2)`
- Gold margin percentages: `DECIMAL(18,4)`

No inspected money column used a binary floating-point type.

## Local/cloud parity

| Control | Local oracle | Local Spark | Workspace Delta | Cloud difference |
|---|---:|---:|---:|---:|
| Trusted invoices | 720 | 720 | 720 | 0 |
| Trusted operational costs | 2,880 | 2,880 | 2,880 | 0 |
| Revenue (EUR) | 916,351.47 | 916,351.47 | 916,351.47 | 0.00 |
| Operational cost (EUR) | 230,279.65 | 230,279.65 | 230,279.65 | 0.00 |
| Gross profit (EUR) | 686,071.82 | 686,071.82 | 686,071.82 | 0.00 |
| Budget (EUR) | 3,048,056.60 | 3,048,056.60 | 3,048,056.60 | 0.00 |

| Gold contract | Local rows | Local Spark rows | Workspace rows |
|---|---:|---:|---:|
| `gold_monthly_country_finance` | 60 | 60 | 60 |
| `gold_route_profitability` | 120 | 120 | 120 |
| `gold_customer_profitability` | 240 | 240 | 240 |
| `gold_budget_vs_actual` | 120 | 120 | 120 |
| `gold_data_quality_summary` | 38 | 38 | 38 |

Silver and Gold independently returned identical revenue and operational-cost totals. Both
`reconciliation_controls` rows returned `matches=true`; failed quality controls and failed
quality rows were zero.

## Correction evidence

Both generated correction manifests use `batch_id=milestone1-correction` and explicitly declare
`supersedes_batch_id=slice001-healthy`. The declaration authorizes only the focused baseline
ownership transfer. Any undeclared financial-key owner still fails closed before fact
publication.

| Item | Initial | Corrected |
|---|---:|---:|
| Run ID | `586763144261151` | `176675503042120` |
| Started | `2026-07-24T20:17:31Z` | `2026-07-24T20:23:58Z` |
| Completed | `2026-07-24T20:22:18Z` | `2026-07-24T20:28:31Z` |
| Duration | 286.6 seconds | 272.8 seconds |
| Final state | SUCCESS | SUCCESS |
| Trusted invoice rows | 720 | 720 |
| Trusted operational-cost rows | 2,879 | 2,880 |
| Unique cost IDs | 2,879 | 2,880 |
| Revenue (EUR) | 916,351.47 | 916,351.47 |
| Global operational cost (EUR) | 230,238.08 | 230,279.65 |
| Global gross profit (EUR) | 686,113.39 | 686,071.82 |
| January DE operational cost (EUR) | 2,941.53 | 2,983.10 |
| January DE gross profit (EUR) | 13,918.31 | 13,876.74 |
| Failed reconciliation controls | 0 | 0 |

All three tasks succeeded in both runs. The corrected cost delta is EUR 41.57, invoice revenue is
unchanged, and active financial ownership remains `milestone1-correction`.

Bronze evidence remained immutable: after healthy, initial correction, and corrected correction,
the operational-cost Bronze table retained 8,639 rows and the invoice Bronze table retained
2,160 rows. The final trusted contribution contains 2,880 unique costs and 720 invoices.

The data-quality Gold contract contains 76 rows after correction because it retains the 38
healthy control rows and the 38 correction-owner control rows. The four financial Gold contracts
retain their documented row counts.

## Repository quality gate

```powershell
python -m pytest -q --cov=datalibra --cov-report=term --cov-branch --cov-fail-under=90
python -m ruff check .
python -m ruff format --check .
python -m mypy src/datalibra
python -m pip check
```

Results:

- pytest: `157 passed in 501.46s`
- branch-aware coverage: `96.29%`
- Ruff: `All checks passed!`
- format: `97 files already formatted`
- strict mypy: `Success: no issues found in 32 source files`
- dependency check: `No broken requirements found`
- targeted Databricks/generator ownership contracts: `7 passed`

The exact deployed wheel, `datalibra-0.2.0-py3-none-any.whl`, has SHA-256
`68b6a48fd55db1defba7744cb2d94067fad9f0f9c7d8d2e8c16423bcab42d6bf`. A clean virtual
environment installed it without dependencies, passed `pip check`, and generated a healthy batch
from a directory outside the repository checkout.

A benign Windows Py4J shutdown message appeared after pytest had already exited successfully.

## Remaining limitations

- The cloud adapter supports the focused declared supersession but does not yet implement the
  local oracle's generalized attested invoice-claim lifecycle.
- Delta publication is atomic per table; ordered job tasks provide convergence across tables.
- Deterministic source row numbering currently uses an unpartitioned Spark window. This is
  acceptable for the small portfolio batch but requires a scalable ingestion identity strategy
  before high-volume production use.
- Production alerting, retention, optimization, cost controls, and steward workflows require
  workspace-specific policies.
- The monthly opening FX baseline and direct shipment-linked cost allocation require Finance
  approval before production use.

No manual Databricks action remains for the Milestone 1 gate. Milestone 2 may begin.
