# Demo Scenario

## Narrative

A finance analyst receives the complete 2025 regional delivery and proves trusted EUR revenue. Three subsequent demonstrations show how Libra handles a resent invoice, a missing March GBP-rate partition, and a Germany invoice file containing roughly 30% of expected volume.

## Run

```powershell
libra generate healthy --output data/generated
libra run healthy --input data/generated --output data/processed
libra generate broken --output data/generated
libra run broken --input data/generated --output data/processed
pytest tests/demo -q
```

The broken command intentionally returns exit code 2 after writing controlled results. Run each scenario directly when an interactive shell should continue:

```powershell
libra run-batch --batch-dir data/generated/duplicate_invoices --output data/processed/duplicate_invoices
libra run-batch --batch-dir data/generated/missing_gbp_fx --output data/processed/missing_gbp_fx
libra run-batch --batch-dir data/generated/incomplete_germany --output data/processed/incomplete_germany
```

## Talking points

1. Compare source manifest fingerprints to show reproducibility.
2. Trace a row through batch-addressed Bronze provenance.
3. Inspect fixed-scale Silver EUR values and exact-date FX rates.
4. Show quarantined rows and stable reason codes.
5. Show PASS and FAIL rule rows, not just logs.
6. Re-run healthy and demonstrate `already_processed` with unchanged totals.
7. Explain why Databricks transforms once, Snowflake governs/serves, and Power BI calculates presentation measures.

Exact deterministic counts and totals are generated into each run summary and asserted in `tests/demo`; see `demo/expected-results/SLICE_001.md`.
