# Data Model

## Source representation contract

Source calendar dates use unambiguous ISO `YYYY-MM-DD`. Decimal values use a dot radix with no
grouping characters and must be finite. Monetary fact values are non-negative in Slice 001.
Regional slash/dot dates and comma/grouped decimals are rejected rather than guessed.

EUR conversion is stored per transaction at two decimal places with `ROUND_HALF_UP`; aggregates
sum the rounded transaction values. Exchange rates are stored to six decimal places and must be
finite and greater than zero.

## Slice 001 source and Silver entities

| Dataset | Grain | Business key | Important fields |
|---|---|---|---|
| countries | one country | `country_code` | country name, default currency |
| currencies | one currency | `currency_code` | name, decimal places |
| exchange_rates | one currency/day | `rate_date`, `currency_code` | units-to-EUR rate |
| customers | one customer | `customer_id` | name, country code |
| cost_centers | one cost center | `cost_center_id` | name, country code |
| routes | one route | `route_id` | origin/destination, mode, distance, transit days |
| shipments | one shipment | `shipment_id` | date, route, volume, country, customer, cost center, currency, revenue |
| invoices | one invoice | `invoice_id` | shipment, invoice date, dimensions, currency, revenue |
| budgets | one cost-center/month | `month_start`, `cost_center_id` | currency, budget amount |
| operational_costs | one posted cost | `cost_id` | shipment, route, cost center, country, posting date, type, currency, amount |

Silver monetary facts add `amount_eur`, `fx_rate_to_eur`, `_batch_id`, and
`_source_row_number`. Persisted money uses scale 2, FX uses scale 6, shipment volume/distance use
scale 2, and percentages use scale 4.

## Milestone 1 Gold contracts

| Contract | Grain |
|---|---|
| `gold_monthly_country_finance` | calendar month and country |
| `gold_route_profitability` | calendar month and route |
| `gold_customer_profitability` | calendar month and customer |
| `gold_budget_vs_actual` | calendar month and cost center |
| `gold_data_quality_summary` | batch, dataset, and quality rule |

All costs are shipment-linked. Route and customer profitability therefore use direct allocation:
invoice revenue assigned through shipment, less every trusted cost assigned to the same shipment.
Gold control totals must equal committed Silver invoice, operational-cost, and budget totals.

## Planned finance star schema

Dimensions: `DimDate`, `DimCountry`, `DimCustomer`, `DimRoute`, `DimCostCenter`, and `DimCurrency`.

Facts: `FactShipment`, `FactInvoice`, `FactOperationalCost`, `FactBudget`, and `FactDataQualityResult`.

Facts keep their natural event grain. Power BI relationships are single-direction, one-to-many from dimensions to facts. Invoice revenue is the recognized revenue source for financial KPIs; shipment revenue remains an operational comparison and must not be added to invoice revenue.

## Lineage and identity

Every Bronze/Silver/quarantine fact carries a batch ID and source row number. Natural identifiers are deterministic and source-aligned. Warehouse surrogate keys are a Snowflake serving concern and are not fabricated locally.

Invoice business identity is `invoice_id`. Financial claim identity additionally includes the
normalized shipment, invoice/translation date, country, customer, cost center, currency, source
amount, applied FX rate, and translated EUR amount. CSV spelling and file position are not part of
the fingerprint.

Processed state stores immutable batch arrival sequence plus claim and committed-artifact
attestations. Batch-owned claim manifests are trust-critical evidence; the aggregate claim CSV is
a rebuildable index.

## Correction lineage

The focused Milestone 1 correction uses the existing batch identity. A changed fingerprint
replaces only that batch's contribution while preserving arrival sequence and Bronze versions.
The persisted before/after audit identifies the historical country/month and both financial
results. In the cloud demonstration, both generated correction manifests additionally declare
`supersedes_batch_id=slice001-healthy`. This narrowly authorizes the correction batch to replace
the baseline fact contribution already active in Delta; no undeclared owner is eligible for
replacement.
