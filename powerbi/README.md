# Power BI delivery contract

Slice 001 documents the semantic/report contract but does not generate a fake PBIX. The complete PBIP/TMDL artifact requires the Snowflake serving views and visual verification in Power BI Desktop, owned by LIBRA-006.

## Completion workflow in Power BI Desktop

1. Create a PBIP project named `Libra` and connect to the governed Snowflake `REPORTING` views.
2. Rename imported tables to the names in `semantic-model/RELATIONSHIPS.md`.
3. Configure relationships exactly as documented; hide technical keys and raw additive fields from report consumers.
4. Add the measures from `dax/MEASURES.dax` and format EUR/percent/count values.
5. Build pages using `report/PAGE_SPECIFICATIONS.md` and configure transaction-detail drill-through.
6. Reconcile Total Revenue, cost, budget, and quality counts to Snowflake controls.
7. Save as PBIP, inspect the text diff, run a refresh, and capture screenshots/test evidence before merging.

The `.pbip` file/folders will be committed only after Power BI Desktop creates and validates them.
