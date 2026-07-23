# Slice 001 Expected Results

These values are deterministic for seed `20250101` and are asserted by `tests/demo/test_slice_001_scenarios.py`.

| Scenario | Bronze invoices | Silver invoices | Quarantined invoices | Other quarantine | Failed rule | Trusted invoice revenue EUR |
|---|---:|---:|---:|---|---|---:|
| healthy | 720 | 720 | 0 | none | none | 916,351.47 |
| duplicate invoices | 732 | 720 | 12 | none | `DUPLICATE_INVOICE` | 916,351.47 |
| missing GBP FX | 720 | 708 | 12 | 12 shipments, 2 budgets, 48 costs | `EXCHANGE_RATE_EXISTS` | 900,446.34 |
| incomplete Germany | 619 | 576 | 43 | none | `INVOICE_COUNTRY_VOLUME` | 697,854.41 |
| invalid operational costs | 720 | 720 | 0 | 9 costs | cost/FX/reference rules | 916,351.47 |

Additional fixed counts are 5 countries, 3 currencies, 20 customers, 10 cost centers, 10 routes,
720 shipments, 2,880 operational costs, and 120 budgets before scenario-specific quarantine.
Healthy FX contains 1,095 daily currency rows. The missing-FX scenario removes the 31 GBP rates
for March and therefore contains 1,064 FX rows.

Healthy Gold controls are revenue `916351.47`, operational cost `230279.65`, gross profit
`686071.82`, and budget `3048056.60`. Row counts are 60 monthly-country, 120 route, 240 customer,
120 budget-versus-actual, and 38 shared business data-quality rows. Fourteen local post-write
reconciliation checks remain in the quality/audit evidence rather than becoming additional Gold
contract rows.

## Interpretation

- The 12 resent invoice occurrences remain in Bronze and quarantine; only the original 720 invoice identities enter Silver, so revenue is unchanged.
- Missing March GBP rates prevent 12 UK shipments, 12 UK invoices, 2 UK monthly budgets, and 48
  UK costs from receiving trusted EUR values.
- Germany delivers 43 of 144 expected invoices (29.9%, approximately 70% fewer). Because the configured minimum is 50%, all 43 delivered Germany invoice rows are quarantined as an incomplete partition. The other countries' 576 invoices remain trusted.
- Every scenario must pass row-count and convertible-financial-total reconciliation because quarantined records are explicitly accounted for.
- Re-running the unchanged healthy batch returns `already_processed`, retaining 720 Silver invoices and the exact revenue above.
- The focused correction adds one January DE fuel posting, changes historical cost/profit by
  `41.57`, preserves arrival sequence, and retains 720 invoices plus 2,880 unique cost IDs.
