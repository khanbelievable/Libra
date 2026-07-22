# Slice 001 Engineering Review

> Historical baseline: this implementer review describes commit `40ac981`. The independent
> findings and Slice 001.1 disposition are in [`REVIEW_LOG.md`](REVIEW_LOG.md), and the current
> release evidence is in
> [`handoffs/CODEX_REMEDIATION_SLICE_001_1.md`](handoffs/CODEX_REMEDIATION_SLICE_001_1.md).

## Delivered

- Deterministic 2025 data for five countries and three transaction currencies.
- Healthy, duplicate-invoice, missing-GBP-FX, and incomplete-Germany deliveries.
- Manifest validation, payload fingerprints, immutable Bronze versions, standardized Silver data, quarantine, quality results, reconciliation, and refresh state.
- Exact `Decimal` EUR conversion using the transaction date.
- Unchanged-batch no-op replay and corrected-batch replacement.
- Local CLI plus unit, integration, contract, and demo test suites.
- Reviewed contracts for the later Databricks, Snowflake, and Power BI implementations.

## Verification baseline

Verified on Python 3.12:

```text
pytest -q
25 passed

pytest -q --cov=datalibra --cov-report=term
94% branch-aware coverage

ruff check .
All checks passed

ruff format --check .
All files formatted

mypy src/datalibra
Success: no issues found in 19 source files

pip check
No broken requirements found
```

The demo baseline is 720 trusted healthy invoices and EUR 916,351.47 revenue. Exact failure counts and totals are maintained in `demo/expected-results/SLICE_001.md` and asserted in `tests/demo`.

## Decisions made in this slice

- `rate_to_eur` is the EUR value of one source-currency unit.
- Invoice date selects the daily rate in the reference implementation.
- The first occurrence of a duplicated invoice ID remains trusted; later occurrences are quarantined.
- A country below 50% of its configured annual baseline is withheld as an incomplete partition.
- Quality failures persist evidence and return CLI exit code 2; execution failures raise an exception.
- Batch ID and content fingerprint distinguish a no-op resend from a correction.

## Known boundaries

- The real PySpark/Delta adapter and Databricks deployment have not been implemented or cloud-tested.
- Snowflake objects and grants have not been deployed.
- The Power BI semantic/report definitions have not been materialized as a PBIP project or visually tested in Desktop.
- Routes, operational cost transactions, Gold profitability aggregates, and late-arriving invoice scenarios are planned later slices.
- Local publication is atomic per output file, not across the entire batch. Delta is the intended production transaction boundary.
- The demo volume baseline is static; production needs an approved historical and holiday-aware policy.

## Review questions

1. Should an incomplete country partition hold only that country or the complete invoice batch?
2. Should finance translation use invoice date, posting date, shipment date, or an approved month-end rate?
3. Should all occurrences of a duplicated invoice ID be withheld instead of trusting the first?
4. What historical window and holiday controls should replace the static volume baseline?

## Recommended next slice

Add route definitions and fuel, labor, warehousing, and transport cost transactions. Reconcile those costs, then publish customer, route, country, and cost-center profitability aggregates.
