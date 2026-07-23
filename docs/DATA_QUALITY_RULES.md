# Data Quality Rules

| Rule name | Reason code | Dataset | Behavior | Severity |
|---|---|---|---|---|
| Duplicate invoice | `DUPLICATE_INVOICE` | invoices | Within one batch, keep the first identical claim and quarantine later occurrences | error |
| Cross-batch invoice replay | `CROSS_BATCH_DUPLICATE_INVOICE` | invoices | Preserve the earliest active owner; quarantine the redelivery | error |
| Conflicting invoice claim | `CONFLICTING_DUPLICATE_INVOICE` | invoices | Withhold every occurrence until an owning batch is corrected | error |
| Cross-batch fact replay | `CROSS_BATCH_RECORD_OWNERSHIP` | shipments/budgets | Preserve the first owner and quarantine an exact later replay | warning |
| Required customer | `MISSING_CUSTOMER_ID` | shipments/invoices | Quarantine row | error |
| Required cost center | `MISSING_COST_CENTER_ID` | shipments/invoices/budgets | Quarantine row | error |
| Finite financial value | `INVALID_FINANCIAL_VALUE` | monetary facts | Reject malformed, non-finite, or forbidden negative values | error |
| Valid exchange rate | `INVALID_EXCHANGE_RATE` / `INVALID_EXCHANGE_RATE_REFERENCE` | FX/facts | Rate must be finite and greater than zero; withhold dependent facts | error |
| Exchange-rate uniqueness | `DUPLICATE_EXCHANGE_RATE` / `CONFLICTING_EXCHANGE_RATE` / `CONFLICTING_EXCHANGE_RATE_REFERENCE` | FX/facts | Deduplicate one exact rate; withhold a contested rate key and dependents | error |
| Exchange rate exists | `MISSING_EXCHANGE_RATE` | monetary facts | Quarantine; do not calculate/trust EUR amount | error |
| Country invoice volume | `COUNTRY_VOLUME_DROP` | invoices | If delivered count is below 50% of configured expected count, quarantine that country partition | error |
| Country reference | `UNKNOWN_COUNTRY_CODE` | dimensions/facts | Quarantine row | error |
| Currency reference | `UNKNOWN_CURRENCY_CODE` | dimensions/facts | Quarantine row | error |
| Customer reference | `UNKNOWN_CUSTOMER_ID` | shipments/invoices | Quarantine row | error |
| Cost-center reference | `UNKNOWN_COST_CENTER_ID` | facts | Quarantine row | error |
| Shipment reference | `UNKNOWN_SHIPMENT_ID` | invoices | Quarantine row | error |
| Row reconciliation | `COMMITTED_READBACK_MISMATCH` | all | Committed batch counts, business keys, and quarantine evidence must match expected publication | error |
| Financial reconciliation | `COMMITTED_FINANCIAL_MISMATCH` | monetary facts | Committed batch and global EUR totals must match expected totals | error |

Quality result fields are: rule name, affected dataset, batch ID, failure reason, failed-row count, affected financial amount where calculable, deterministic execution timestamp, and `PASS`/`FAIL`. Zero-failure PASS rows are stored so coverage is auditable.

Multiple reason codes may apply to one quarantined row. No row with a row-level error reason
enters Silver. Dataset-level volume failures protect against apparently valid but incomplete
partitions. Volume counts distinct invoice IDs and compares an exact Decimal threshold. The local
implementation uses configured expected counts; production will use an approved trailing-history
baseline with minimum history and holiday overrides.

Quality and quarantine evidence has per-batch audit grain, including a redelivery under a new
batch ID. Steward metrics for distinct issues must count distinct business keys, not raw evidence
rows.

Valid rows from a controlled `quality_failed` batch are published, while invalid rows remain in
quarantine. The batch remains visible in quality history but does not advance the trusted refresh
timestamp. Direct consumers of local Silver must therefore apply the processed-state refresh gate;
the future Delta adapter will provide transactional release semantics.

Cross-batch shipment and budget payloads are normalized before comparison. An exact repeat emits
noncritical ownership evidence and leaves the first contribution unchanged. A conflicting
monetary payload raises `CrossBatchCollisionError`; it is an execution failure, not a row-quality
result, because Slice 001.2 does not define a generalized non-invoice correction policy.

Claim-manifest, state, and committed-artifact attestation failures are likewise execution
failures. They use typed integrity errors and must not publish trusted state. Dimension and
exchange-rate reference ownership remains outside the Slice 001.2 claim architecture.
