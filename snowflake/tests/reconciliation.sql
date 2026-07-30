-- Returns one row per blocking control. Every DIFFERENCE must be zero.
WITH ACTUAL AS (
    SELECT 'invoice_count' CONTROL_NAME, COUNT(*)::NUMBER(38,2) ACTUAL_VALUE
      FROM LIBRA.CORE.FACT_INVOICE
    UNION ALL SELECT 'operational_cost_count', COUNT(*) FROM LIBRA.CORE.FACT_OPERATIONAL_COST
    UNION ALL SELECT 'revenue_eur', SUM(AMOUNT_EUR) FROM LIBRA.CORE.FACT_INVOICE
    UNION ALL SELECT 'operational_cost_eur', SUM(AMOUNT_EUR)
      FROM LIBRA.CORE.FACT_OPERATIONAL_COST
    UNION ALL SELECT 'gross_profit_eur',
      (SELECT SUM(AMOUNT_EUR) FROM LIBRA.CORE.FACT_INVOICE)
      - (SELECT SUM(AMOUNT_EUR) FROM LIBRA.CORE.FACT_OPERATIONAL_COST)
    UNION ALL SELECT 'budget_eur', SUM(AMOUNT_EUR) FROM LIBRA.CORE.FACT_BUDGET
    UNION ALL SELECT 'monthly_country_finance_count',COUNT(*)
      FROM LIBRA.REPORTING.MONTHLY_COUNTRY_FINANCE
    UNION ALL SELECT 'route_profitability_count',COUNT(*)
      FROM LIBRA.REPORTING.ROUTE_PROFITABILITY
    UNION ALL SELECT 'customer_profitability_count',COUNT(*)
      FROM LIBRA.REPORTING.CUSTOMER_PROFITABILITY
    UNION ALL SELECT 'budget_vs_actual_count',COUNT(*) FROM LIBRA.REPORTING.BUDGET_VS_ACTUAL
    UNION ALL SELECT 'healthy_data_quality_count',COUNT(*)
      FROM LIBRA.CORE.FACT_DATA_QUALITY_RESULT WHERE BATCH_ID='slice001-healthy'
    UNION ALL SELECT 'retained_data_quality_count',COUNT(*)
      FROM LIBRA.CORE.FACT_DATA_QUALITY_RESULT
    UNION ALL SELECT 'duplicate_invoice_ids',COUNT(*)-COUNT(DISTINCT INVOICE_ID)
      FROM LIBRA.CORE.FACT_INVOICE
    UNION ALL SELECT 'duplicate_cost_ids',COUNT(*)-COUNT(DISTINCT COST_ID)
      FROM LIBRA.CORE.FACT_OPERATIONAL_COST
    UNION ALL SELECT 'duplicate_shipment_ids',COUNT(*)-COUNT(DISTINCT SHIPMENT_ID)
      FROM LIBRA.CORE.FACT_SHIPMENT
), EXPECTED AS (
    SELECT COLUMN1 CONTROL_NAME, COLUMN2::NUMBER(38,2) EXPECTED_VALUE FROM VALUES
      ('invoice_count',720),('operational_cost_count',2880),('revenue_eur',916351.47),
      ('operational_cost_eur',230279.65),('gross_profit_eur',686071.82),
      ('budget_eur',3048056.60),('monthly_country_finance_count',60),
      ('route_profitability_count',120),('customer_profitability_count',240),
      ('budget_vs_actual_count',120),('healthy_data_quality_count',38),
      ('retained_data_quality_count',76),('duplicate_invoice_ids',0),
      ('duplicate_cost_ids',0),('duplicate_shipment_ids',0)
)
SELECT E.CONTROL_NAME,E.EXPECTED_VALUE,A.ACTUAL_VALUE,
       (A.ACTUAL_VALUE-E.EXPECTED_VALUE)::NUMBER(38,2) DIFFERENCE,
       IFF(A.ACTUAL_VALUE=E.EXPECTED_VALUE,'PASS','FAIL') STATUS
FROM EXPECTED E JOIN ACTUAL A USING(CONTROL_NAME)
ORDER BY E.CONTROL_NAME;
