# Data Model

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
