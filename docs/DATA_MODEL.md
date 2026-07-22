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
| shipments | one shipment | `shipment_id` | date, country, customer, cost center, currency, revenue |
| invoices | one invoice | `invoice_id` | shipment, invoice date, dimensions, currency, revenue |
| budgets | one cost-center/month | `month_start`, `cost_center_id` | currency, budget amount |

Silver monetary facts add `amount_eur`, `fx_rate_to_eur`, `_batch_id`, and `_source_row_number`. Persisted decimal strings have two digits for money and six for rates.

## Planned finance star schema

Dimensions: `DimDate`, `DimCountry`, `DimCustomer`, `DimRoute`, `DimCostCenter`, and `DimCurrency`.

Facts: `FactShipment`, `FactInvoice`, `FactOperationalCost`, `FactBudget`, and `FactDataQualityResult`.

Facts keep their natural event grain. Power BI relationships are single-direction, one-to-many from dimensions to facts. Invoice revenue is the recognized revenue source for financial KPIs; shipment revenue remains an operational comparison and must not be added to invoice revenue.

## Lineage and identity

Every Bronze/Silver/quarantine fact carries a batch ID and source row number. Natural identifiers are deterministic and source-aligned. Warehouse surrogate keys are a Snowflake serving concern and are not fabricated locally.

## Future entities

Routes and operational costs enter Slice 002. Their planned grains are one route definition and one posted operational-cost transaction. Late-arrival metadata and correction lineage extend the existing batch fields rather than creating a second processing path.
