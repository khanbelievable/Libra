# Milestone 1 Validation

Validation date: 2026-07-23  
Reference environment: Windows, Python 3.12.13, PySpark 4.1.3, Java 21, Databricks CLI 1.9.0

## Status

| Gate | Status | Evidence |
|---|---|---|
| Deterministic local Bronze/Silver/Gold | PASS | healthy, four broken scenarios, and correction executed from the installed wheel |
| Local PySpark contracts | PASS | explicit schemas, quarantine, DQ summary, DecimalType finance, and Gold parity |
| Python wheel | PASS | `datalibra-0.2.0-py3-none-any.whl`, SHA-256 `8632ff6887aa3418fd198da7392bd8ea3669a46a1bb1500e63d4557b4c8080b3` |
| Bundle configuration parse | PASS | CLI identified bundle `libra-milestone-1`, target `prod`, and the configured workspace path |
| Authenticated bundle validation | BLOCKED | no Databricks profile or unified-auth credentials are present |
| Bundle deployment | NOT RUN | depends on authenticated validation |
| Workspace job execution | NOT RUN | depends on deployment |
| Delta inspection and cloud/local comparison | NOT RUN | depends on a completed workspace run |

Milestone 1 is locally verified and deployable, but it is not represented as cloud-complete.

## Commands and results

Release test and coverage gate:

```powershell
python -m pytest -q --cov=datalibra --cov-report=term --cov-branch --cov-fail-under=90
```

Result: `154 passed in 684.28s`; total branch-aware coverage `96.29%`. The two omitted modules,
`datalibra.databricks.delta` and `datalibra.databricks.tasks`, are workspace/Delta publication
adapters that require a Delta runtime. Their locally executable schemas, transformations, Gold
logic, and bundle contracts remain measured. A benign Windows Py4J shutdown message appeared
after pytest had exited successfully.

Independent gates:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy src/datalibra
python -m pip check
```

Results:

- Ruff: `All checks passed!`
- format: `57 files already formatted`
- strict mypy: `Success: no issues found in 32 source files`
- dependency check: `No broken requirements found`

Wheel build and isolated installation:

```powershell
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir <validation-root>/wheel
python -m venv <validation-root>/venv
<validation-root>/venv/Scripts/python -m pip install <validation-root>/wheel/datalibra-0.2.0-py3-none-any.whl
<validation-root>/venv/Scripts/python -m pip check
```

Result: version `0.2.0` built, installed, and passed dependency validation.

Installed CLI analytics:

```powershell
libra generate healthy --output <validation-root>/generated
libra run healthy --input <validation-root>/generated --output <validation-root>/processed
libra generate broken --output <validation-root>/generated
libra run broken --input <validation-root>/generated --output <validation-root>/processed
libra generate correction --output <validation-root>/generated
libra run correction --input <validation-root>/generated --output <validation-root>/processed
```

Results:

- healthy: exit `0`, status `success`
- broken: exit `2` as designed; all four scenarios reported `quality_failed`
- correction: exit `0`, both owner-scoped runs reported `success`

Local Spark contract command:

```powershell
python -m pytest tests/contract/test_pyspark_milestone1.py -q
```

Result: `3 passed in 170.27s`. The contract covers every source/Bronze schema, healthy and broken
Silver behavior, the 38-row shared DQ contract, fixed-scale Spark types, and Spark/local financial
parity. A benign Windows Spark cleanup message followed the successful pytest result.

Databricks CLI boundary:

```powershell
databricks version
databricks auth profiles
databricks bundle validate --target prod `
  --var "catalog=main" `
  --var "landing_path=/Volumes/main/libra/landing/healthy"
```

Result:

```text
Databricks CLI v1.9.0
no configuration file found at C:\Users\KAAN\.databrickscfg
Name: libra-milestone-1
Target: prod
Workspace path: /Workspace/Shared/.bundle/${bundle.name}/${bundle.target}
Found 1 error: default auth cannot configure credentials
```

The bundle parsed successfully before the CLI reached its authentication-dependent request
visitor. This is not recorded as authenticated bundle validation.

## Gold controls

The local oracle and local Spark execution agree:

| Control | Local oracle (EUR) | Local Spark (EUR) | Workspace Delta (EUR) |
|---|---:|---:|---:|
| Revenue | 916,351.47 | 916,351.47 | not run |
| Operational cost | 230,279.65 | 230,279.65 | not run |
| Gross profit | 686,071.82 | 686,071.82 | not run |
| Budget | 3,048,056.60 | 3,048,056.60 | not run |

| Gold contract | Grain | Local rows | Local Spark rows | Workspace rows |
|---|---|---:|---:|---:|
| `gold_monthly_country_finance` | month, country | 60 | 60 | not run |
| `gold_route_profitability` | month, route | 120 | 120 | not run |
| `gold_customer_profitability` | month, customer | 240 | 240 | not run |
| `gold_budget_vs_actual` | month, cost center | 120 | 120 | not run |
| `gold_data_quality_summary` | batch, dataset, shared business rule | 38 | 38 | not run |

The 14 local post-write reconciliation checks stay in audit-quality evidence and are not extra
Gold rows. Databricks writes reconciliation evidence to the non-Gold
`reconciliation_controls` table.

## Correction evidence

Both arrivals use `batch_id=milestone1-correction` and arrival sequence `1`.

| Control | Initial | Corrected |
|---|---:|---:|
| Trusted operational-cost rows | 2,879 | 2,880 |
| January DE operational cost (EUR) | 2,941.53 | 2,983.10 |
| January DE gross profit (EUR) | 13,918.31 | 13,876.74 |
| Global operational cost (EUR) | 230,238.08 | 230,279.65 |
| Global gross profit (EUR) | 686,113.39 | 686,071.82 |

The corrected cost delta is EUR 41.57. Trusted cost IDs are unique, and trusted invoice count
remains 720.

## Expected Delta tables

After an authenticated run, inspect these tables in `<catalog>.libra`:

- Bronze: `bronze_countries`, `bronze_currencies`, `bronze_customers`,
  `bronze_cost_centers`, `bronze_routes`, `bronze_exchange_rates`, `bronze_shipments`,
  `bronze_invoices`, `bronze_budgets`, `bronze_operational_costs`
- Silver: the same ten dataset names prefixed with `silver_`
- Quarantine: the same ten dataset names prefixed with `quarantine_`
- Quality/audit: `quality_results`, `reconciliation_controls`
- Gold: exactly the five contracts listed above

## Remaining workspace actions

Follow [DATABRICKS_RUNBOOK.md](DATABRICKS_RUNBOOK.md) to:

1. authenticate the CLI to the intended workspace;
2. rerun `databricks bundle validate`;
3. deploy and run job `milestone_1`;
4. record the run ID or safe display URL;
5. inspect Bronze, Silver, quarantine, quality/audit, and all five Gold tables;
6. populate the Workspace columns above and confirm the two reconciliation controls are true;
7. run both correction inputs with the same batch ID and capture the historical Delta change.

Milestone 2 must not begin until those authenticated workspace actions pass.

## Known limitations

- The cloud fact guard fails closed when another batch owns a financial natural key. The local
  oracle has a richer attested invoice-claim lifecycle.
- Delta publication is atomic per table; ordered job tasks provide convergence across tables.
- Production alerting, retention, optimization, cost controls, and steward workflows require
  workspace-specific policies.
- The monthly opening FX baseline and direct shipment-linked cost allocation require Finance
  approval before production use.
