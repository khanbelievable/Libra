# Databricks Delta implementation

Milestone 1 includes an executable PySpark/Delta path and a Databricks Declarative Automation
Bundle. The local Python pipeline remains the deterministic financial oracle.

The bundle deploys one job with three wheel tasks:

1. `land_bronze` validates the source manifest and idempotently appends immutable batch/fingerprint
   evidence to Bronze Delta tables.
2. `build_silver` applies explicit schemas, identifier/date standardization, DecimalType finance
   casts, FX conversion, referential checks, cost quarantine, and batch-owned Delta MERGE.
3. `build_gold_and_validate` publishes the five Gold Delta contracts and an audit reconciliation
   table;
   the task fails if revenue or operational cost differs from trusted Silver.

Conformed reference tables use global natural keys. Financial fact merges replace only the current
batch contribution. A natural key already owned by another batch fails closed before fact
publication; the local claim engine remains the richer cross-batch invoice oracle.

Deployment, inspection, correction, and cleanup commands are in
[`docs/DATABRICKS_RUNBOOK.md`](../docs/DATABRICKS_RUNBOOK.md). Actual workspace status and control
totals are recorded in [`docs/MILESTONE_1_VALIDATION.md`](../docs/MILESTONE_1_VALIDATION.md).
