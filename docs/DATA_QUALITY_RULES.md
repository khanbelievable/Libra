# Data Quality Rules

| Rule name | Reason code | Dataset | Behavior | Severity |
|---|---|---|---|---|
| Duplicate invoice | `DUPLICATE_INVOICE` | invoices | Keep deterministic first occurrence; quarantine later occurrences | error |
| Required customer | `MISSING_CUSTOMER_ID` | shipments/invoices | Quarantine row | error |
| Required cost center | `MISSING_COST_CENTER_ID` | shipments/invoices/budgets | Quarantine row | error |
| Exchange rate exists | `MISSING_EXCHANGE_RATE` | monetary facts | Quarantine; do not calculate/trust EUR amount | error |
| Country invoice volume | `COUNTRY_VOLUME_DROP` | invoices | If delivered count is below 50% of configured expected count, quarantine that country partition | error |
| Customer reference | `UNKNOWN_CUSTOMER_ID` | shipments/invoices | Quarantine row | error |
| Cost-center reference | `UNKNOWN_COST_CENTER_ID` | facts | Quarantine row | error |
| Shipment reference | `UNKNOWN_SHIPMENT_ID` | invoices | Quarantine row | error |
| Row reconciliation | `ROW_COUNT_MISMATCH` | all | Batch source count must equal trusted plus quarantined count | error |
| Financial reconciliation | `FINANCIAL_TOTAL_MISMATCH` | monetary facts | Convertible source EUR must equal trusted plus convertible quarantine EUR | error |

Quality result fields are: rule name, affected dataset, batch ID, failure reason, failed-row count, affected financial amount where calculable, deterministic execution timestamp, and `PASS`/`FAIL`. Zero-failure PASS rows are stored so coverage is auditable.

Multiple reason codes may apply to one quarantined row. No row with any error reason enters Silver. Dataset-level volume failures protect against apparently valid but incomplete partitions. The local implementation uses configured expected counts; production will use an approved trailing-history baseline with minimum history and holiday overrides.

The latest successful refresh is the most recent batch whose processing completed and whose critical rules passed. Controlled quality-failed batches remain visible in quality history but do not advance the trusted refresh timestamp.
