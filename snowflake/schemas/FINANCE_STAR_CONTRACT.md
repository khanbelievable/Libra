# Finance Star Contract

Implemented dimensions: `DIM_DATE`, `DIM_COUNTRY`, `DIM_CUSTOMER`, `DIM_ROUTE`,
`DIM_COST_CENTER`, and `DIM_CURRENCY`.

Implemented facts: `FACT_SHIPMENT`, `FACT_INVOICE`, `FACT_OPERATIONAL_COST`, `FACT_BUDGET`,
and `FACT_DATA_QUALITY_RESULT`.

All finance facts retain source natural IDs, Databricks batch ID, event/posting date, original currency/amount, applied FX rate, and EUR amount. `FACT_DATA_QUALITY_RESULT` follows the fields in `docs/DATA_QUALITY_RULES.md`. Warehouse load audit stores contract version, Gold extract count/total, Snowflake count/total, load timestamp, and status.

Power BI receives stable `REPORTING` views rather than base-table ownership. The executable
contract is in `snowflake/migrations`; credential-free enforcement is in
`tests/contract/test_snowflake_sql_contract.py`.
