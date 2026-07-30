# Power BI project

`powerbi/Libra/Libra.pbip` is a real source-controlled Power BI Project:

```text
Libra.pbip
Libra.SemanticModel/
  definition.pbism
  definition/*.tmdl
  definition/tables/*.tmdl
Libra.Report/
  definition.pbir
  definition/report.json
  definition/pages/*/page.json
  definition/pages/*/visuals/*/visual.json
```

The semantic model imports stable Snowflake `LIBRA.REPORTING` views through two required text
parameters: `SnowflakeServer` and `SnowflakeWarehouse`. Placeholder values contain no account or
identity data. The model has 12 tables, 22 one-direction dimension-to-fact relationships, and the
14 approved measures from `dax/MEASURES.dax`. Technical keys and additive source columns used by
explicit measures are hidden.

The PBIR report contains seven ordered pages with data-bound KPI, chart/table, date, and country
visuals:

1. Executive Overview
2. Country Performance
3. Customer and Route Profitability
4. Budget vs Actual
5. Cost Drivers and FX Impact
6. Data Quality and Refresh Status
7. Drill-through Transaction Detail

Microsoft's `@microsoft/powerbi-report-authoring-cli` validates the project with zero errors and
zero warnings. This is source validation, not a claim that DAX executed or visuals rendered.

## Required Desktop gate

Power BI Desktop was not installed on the implementation machine. After Snowflake deployment:

1. Install a current Power BI Desktop build that supports PBIP/TMDL/PBIR.
2. Open `Libra.pbip`, set `SnowflakeServer` and `SnowflakeWarehouse`, and authenticate with only
   the finance/DQ reader roles.
3. Refresh and verify EUR 916,351.47 revenue, EUR 230,279.65 cost, EUR 686,071.82 gross profit,
   and EUR 3,048,056.60 budget.
4. Confirm 22 active single-direction relationships, 14 error-free measures, seven pages,
   slicer interactions, route/customer filtering, DQ history, refresh status, and transaction
   drill-through.
5. Inspect every page at Fit to page and capture one screenshot per page under
   `docs/evidence/milestone-2/`.

Do not mark Milestone 2 complete until that runtime evidence and Snowflake reconciliation are
returned.
