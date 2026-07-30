# Semantic Model Relationships

Use one-to-many, single-direction filtering from dimensions to facts.

| From (one) | To (many) | Fact column | Active |
|---|---|---|---|
| DimDate[DateKey] | FactShipment | ShipmentDateKey | yes |
| DimDate[DateKey] | FactInvoice | InvoiceDateKey | yes |
| DimDate[DateKey] | FactOperationalCost | PostingDateKey | yes |
| DimDate[DateKey] | FactBudget | MonthDateKey | yes |
| DimCountry[CountryKey] | all business facts | CountryKey | yes |
| DimCustomer[CustomerKey] | FactShipment, FactInvoice, FactOperationalCost | CustomerKey | yes |
| DimRoute[RouteKey] | FactShipment, FactInvoice, FactOperationalCost | RouteKey | yes |
| DimCostCenter[CostCenterKey] | FactShipment, FactInvoice, FactOperationalCost, FactBudget | CostCenterKey | yes |
| DimCurrency[CurrencyKey] | monetary facts | CurrencyKey | yes |

`FactDataQualityResult` relates to DimDate by execution date. Dataset/rule attributes may remain degenerate dimensions until their cardinality justifies separate dimensions. Do not create fact-to-fact or bidirectional relationships.

The serving layer derives invoice route and operational-cost customer keys directly from each
record's trusted shipment. This preserves the approved direct allocation and allows
route/customer profitability to filter both recognized revenue and cost without an ambiguous
fact-to-fact path.
