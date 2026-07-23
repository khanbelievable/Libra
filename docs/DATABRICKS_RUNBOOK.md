# Databricks Milestone 1 Runbook

## Prerequisites

- Databricks CLI 0.205 or newer with unified authentication configured.
- A Unity Catalog catalog plus permission to create a schema, tables, and a job.
- A Unity Catalog Volume or workspace-accessible landing directory containing a generated Libra
  batch.
- Serverless jobs enabled, or a workspace policy that supplies equivalent compatible compute.

Do not store a host, token, client secret, or profile credential in this repository. Authenticate
with a local profile, OAuth, workload identity, or secret-backed CI environment variables.

For non-interactive CI, inject `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, and
`DATABRICKS_CLIENT_SECRET` from the CI secret store. For an interactive workstation, prefer
`databricks auth login --host <workspace-url>` and keep the generated profile outside the
repository. The bundle itself requires no application secret.

## Prepare the source and wheel

```powershell
python -m pip install -e ".[dev,spark]"
libra generate healthy --output data/generated
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist
```

Upload the complete `data/generated/healthy` directory to a controlled Volume path such as:

```text
/Volumes/<catalog>/<schema>/<landing-volume>/healthy
```

The directory must retain all ten CSV files and `manifest.json`. Do not edit a manifest after
upload; the Bronze task recomputes and verifies its SHA-256 fingerprint.

## Authenticate and validate

```powershell
databricks auth profiles
databricks current-user me
databricks bundle validate --target dev `
  --var "catalog=<catalog>" `
  --var "schema=libra" `
  --var "landing_path=/Volumes/<catalog>/<schema>/<landing-volume>/healthy"
```

Validation is not deployment. Record the CLI version, target, and result in
`docs/MILESTONE_1_VALIDATION.md`.

## Deploy and run

```powershell
databricks bundle deploy --target dev `
  --var "catalog=<catalog>" `
  --var "schema=libra" `
  --var "landing_path=/Volumes/<catalog>/<schema>/<landing-volume>/healthy"

databricks bundle run milestone_1 --target dev `
  --params "landing_path=/Volumes/<catalog>/<schema>/<landing-volume>/healthy,catalog=<catalog>,schema=libra,batch_id=slice001-healthy"
```

Capture the run ID or safe display URL. The tasks must finish in order:

```text
land_bronze -> build_silver -> build_gold_and_validate
```

## Inspect Delta outputs

The job creates these tables under `<catalog>.libra`:

```text
bronze_<dataset>                 one table for each source dataset
silver_<dataset>                 conformed trusted rows
quarantine_<dataset>             rejected rows and reason codes
quality_results                  PASS/FAIL evidence
gold_monthly_country_finance
gold_route_profitability
gold_customer_profitability
gold_budget_vs_actual
gold_data_quality_summary
reconciliation_controls           non-Gold audit evidence
```

Run these controls in a Databricks SQL editor or notebook:

```sql
SELECT COUNT(*) AS trusted_cost_rows,
       SUM(amount_eur) AS operational_cost_eur
FROM <catalog>.libra.silver_operational_costs;

SELECT SUM(amount_eur) AS revenue_eur
FROM <catalog>.libra.silver_invoices;

SELECT SUM(total_revenue_eur) AS revenue_eur,
       SUM(total_operational_cost_eur) AS operational_cost_eur,
       SUM(gross_profit_eur) AS gross_profit_eur
FROM <catalog>.libra.gold_monthly_country_finance;

SELECT * FROM <catalog>.libra.reconciliation_controls ORDER BY metric;
```

For the default seed, compare the cloud result to the local oracle controls in
`docs/MILESTONE_1_VALIDATION.md`. Do not call the deployment verified if either reconciliation row
is false.

## Correction demonstration

Generate and upload both correction directories:

```powershell
libra generate correction --output data/generated
```

Run `cost_correction_initial` first, then `cost_correction_corrected`, both with
`batch_id=milestone1-correction`. The corrected run must keep the same batch owner, replace its
2,879-cost contribution with 2,880 unique costs, change January 2025 DE cost/profit, and leave
invoice revenue unchanged.

## Recovery

- An exact rerun is idempotent at Bronze and Silver.
- A same-batch correction replaces only that batch's fact contribution.
- Delta commits are table-atomic. If a later task fails, correct the cause and rerun the same
  job parameters; Gold is not published until Silver completes.
- A financial natural key owned by another batch fails before Silver fact publication. Resolve
  the source ownership issue rather than changing the batch ID to bypass the guard.

## Teardown

Remove only resources created by the selected bundle target:

```powershell
databricks bundle destroy --target dev `
  --var "catalog=<catalog>" `
  --var "schema=libra" `
  --var "landing_path=/Volumes/<catalog>/<schema>/<landing-volume>/healthy"
```

Bundle destruction removes the deployed job/workspace bundle files, not governed Unity Catalog
data. Drop the development schema only after confirming it contains no unrelated objects:

```sql
DROP SCHEMA IF EXISTS <catalog>.libra CASCADE;
```
