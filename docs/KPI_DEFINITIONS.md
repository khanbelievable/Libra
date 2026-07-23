# KPI Definitions

## Finance rounding policy

`rate_to_eur` is EUR per one source-currency unit. Revenue uses invoice date, operational cost
uses posting date, and budget uses month start. Each transaction is multiplied by its effective
rate and quantized to two decimal places using `ROUND_HALF_UP`; reported totals sum those
already-rounded transaction values. Every platform implementation must match this order.

Percentages are calculated from reconciled EUR totals and stored to four decimal places. Route
and customer cost is the sum of costs directly linked to their shipments; Milestone 1 generates
no shared cost pool.

All reporting currency values are EUR. Unless noted, filters from Date, Country, Customer, Route, Cost Center, and Currency dimensions apply.

| KPI | Business definition and calculation | Grain | Required source fields | Null/edge behavior |
|---|---|---|---|---|
| Total Revenue | Recognized invoiced revenue: `SUM(FactInvoice.AmountEUR)` | invoice | invoice ID/date, amount, currency, FX rate | Quarantined or unconverted invoices excluded; blanks display 0 |
| Total Operational Cost | Posted operating cost: `SUM(FactOperationalCost.AmountEUR)` | cost transaction | cost ID/date/type, amount, currency, FX rate | Missing FX quarantined; blanks display 0 |
| Gross Profit | `Total Revenue - Total Operational Cost` | filter context | revenue and cost measures | Returns revenue when cost is zero |
| Gross Margin Percentage | `Gross Profit / Total Revenue` | filter context | gross profit, revenue | Blank when revenue is zero |
| Shipment Count | Distinct trusted shipments | shipment | shipment ID/date | Excludes quarantined records |
| Revenue per Shipment | `Total Revenue / Shipment Count` | filter context | invoice amount, shipment ID | Blank when shipment count is zero |
| Cost per Shipment | `Total Operational Cost / Shipment Count` | filter context | cost amount, shipment ID | Blank when shipment count is zero |
| Budget Amount | Approved cost-center budget: `SUM(FactBudget.AmountEUR)` | cost center/month | month, cost center, amount, currency, FX | Missing FX budgets excluded and flagged |
| Actual Cost | Operational cost aligned to posting month/cost center | cost center/month | posting date, cost center, amount EUR | Missing cost center quarantined |
| Budget Variance Amount | `Budget Amount - Actual Cost`; positive is favorable | cost center/month | budget and actual measures | Blank if no budget exists |
| Budget Variance Percentage | `(Budget Amount - Actual Cost) / Budget Amount` | cost center/month | budget and variance | Blank when budget is zero/missing |
| FX Impact | Revenue translation variance minus cost translation variance. Each variance is actual transaction EUR less source amount translated at the first available rate in that transaction's calendar month | transaction aggregated to month/country | source amount, transaction rate, month-opening rate, EUR amount | Missing-FX facts are quarantined; finance approval of the comparison baseline remains required |

Milestone 1 materializes every KPI above in `gold_monthly_country_finance` and the applicable
profitability or budget contract. Positive budget variance is favorable:
`Budget Amount - Actual Cost`.
