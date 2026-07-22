# Slice 001 Expected Results

These values are deterministic for seed `20250101` and are asserted by `tests/demo/test_slice_001_scenarios.py`.

| Scenario | Bronze invoices | Silver invoices | Quarantined invoices | Other quarantine | Failed rule | Trusted invoice revenue EUR |
|---|---:|---:|---:|---|---|---:|
| healthy | 720 | 720 | 0 | none | none | 916,351.47 |
| duplicate invoices | 732 | 720 | 12 | none | `DUPLICATE_INVOICE` | 916,351.47 |
| missing GBP FX | 720 | 708 | 12 | 12 shipments, 2 budgets | `EXCHANGE_RATE_EXISTS` | 900,446.34 |
| incomplete Germany | 619 | 576 | 43 | none | `INVOICE_COUNTRY_VOLUME` | 697,854.41 |

Additional fixed counts in every scenario are 5 countries, 3 currencies, 20 customers, 10 cost centers, 720 shipments, and 120 budgets before scenario-specific FX quarantine. Healthy FX contains 1,095 daily currency rows. The missing-FX scenario removes the 31 GBP rates for March and therefore contains 1,064 FX rows.

## Interpretation

- The 12 resent invoice occurrences remain in Bronze and quarantine; only the original 720 invoice identities enter Silver, so revenue is unchanged.
- Missing March GBP rates prevent 12 UK shipments, 12 UK invoices, and 2 UK monthly budgets from receiving trusted EUR values.
- Germany delivers 43 of 144 expected invoices (29.9%, approximately 70% fewer). Because the configured minimum is 50%, all 43 delivered Germany invoice rows are quarantined as an incomplete partition. The other countries' 576 invoices remain trusted.
- Every scenario must pass row-count and convertible-financial-total reconciliation because quarantined records are explicitly accounted for.
- Re-running the unchanged healthy batch returns `already_processed`, retaining 720 Silver invoices and the exact revenue above.
