# Demo Scenario

## Narrative

A finance analyst receives the complete 2025 regional delivery and proves trusted EUR revenue,
operational cost, route/customer profitability, and budget variance. Controlled demonstrations
cover resent invoices, missing GBP rates, incomplete Germany delivery, invalid costs, and one
historical cost correction.

## Run

```powershell
libra generate healthy --output data/generated
libra run healthy --input data/generated --output data/processed
libra generate broken --output data/generated
libra run broken --input data/generated --output data/processed
libra generate correction --output data/generated
libra run correction --input data/generated --output data/processed
pytest tests/demo -q
```

The broken command intentionally returns exit code 2 after writing controlled results. Run each scenario directly when an interactive shell should continue:

```powershell
libra run-batch --batch-dir data/generated/duplicate_invoices --output data/processed/duplicate_invoices
libra run-batch --batch-dir data/generated/missing_gbp_fx --output data/processed/missing_gbp_fx
libra run-batch --batch-dir data/generated/incomplete_germany --output data/processed/incomplete_germany
libra run-batch --batch-dir data/generated/invalid_operational_costs --output data/processed/invalid_operational_costs
```

## Talking points

1. Compare source manifest fingerprints to show reproducibility.
2. Trace a row through batch-addressed Bronze provenance.
3. Inspect fixed-scale Silver EUR values and exact-date FX rates.
4. Show quarantined rows and stable reason codes.
5. Show PASS and FAIL rule rows, not just logs.
6. Re-run healthy and demonstrate `already_processed` with unchanged totals.
7. Reconcile all five Gold contracts to Silver revenue, cost, and budget controls.
8. Show the correction before/after audit and unchanged owner sequence.
9. Explain the three-task Delta job and distinguish local, validated, deployed, and executed status.

Exact deterministic counts and totals are generated into each run summary and asserted in `tests/demo`; see `demo/expected-results/SLICE_001.md`.
