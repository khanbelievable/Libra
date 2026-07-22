# KPI Definitions

All reporting currency values are EUR. Unless noted, filters from Date, Country, Customer, Route, Cost Center, and Currency dimensions apply.

| KPI | Business definition and calculation | Grain | Required source fields | Null/edge behavior |
|---|---|---|---|---|
| Total Revenue | Recognized invoiced revenue: `SUM(FactInvoice.AmountEUR)` | invoice | invoice ID/date, amount, currency, FX rate | Quarantined or unconverted invoices excluded; blanks display 0 |
| Total Operational Cost | Posted operating cost: `SUM(FactOperationalCost.AmountEUR)` | cost transaction | cost ID/date/type, amount, currency, FX rate | Missing FX quarantined; blanks display 0 |
| Gross Profit | `Total Revenue - Total Operational Cost` | filter context | revenue and cost measures | Returns revenue when cost is zero |
| Gross Margin Percentage | `Gross Profit / Total Revenue` | filter context | gross profit, revenue | Blank when revenue is zero |
| Shipment Count | Distinct completed shipments | shipment | shipment ID, status/date | Excludes quarantined/cancelled records |
| Revenue per Shipment | `Total Revenue / Shipment Count` | filter context | invoice amount, shipment ID | Blank when shipment count is zero |
| Cost per Shipment | `Total Operational Cost / Shipment Count` | filter context | cost amount, shipment ID | Blank when shipment count is zero |
| Budget Amount | Approved cost-center budget: `SUM(FactBudget.AmountEUR)` | cost center/month | month, cost center, amount, currency, FX | Missing FX budgets excluded and flagged |
| Actual Cost | Operational cost aligned to posting month/cost center | cost center/month | posting date, cost center, amount EUR | Missing cost center quarantined |
| Budget Variance Amount | `Budget Amount - Actual Cost`; positive is favorable | cost center/month | budget and actual measures | Blank if no budget exists |
| Budget Variance Percentage | `(Budget Amount - Actual Cost) / Budget Amount` | cost center/month | budget and variance | Blank when budget is zero/missing |
| FX Impact | Actual EUR amount minus the amount translated at the approved comparison rate | transaction aggregated to context | local amount, actual and comparison FX rates | Blank until comparison-rate policy is configured; never assume zero |

Slice 001 materializes invoice, shipment, and budget EUR values. Operational-cost and comparison-FX inputs arrive in later slices, so affected KPIs remain documented contracts rather than misleading local outputs.
