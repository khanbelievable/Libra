-- Interface contract only; LIBRA-004 will bind these columns to governed Gold Delta views.
-- Snowflake consumes already-conformed values and must not repeat FX or deduplication logic.

SELECT
    invoice_id,
    shipment_id,
    invoice_date,
    country_code,
    customer_id,
    cost_center_id,
    currency_code,
    revenue_amount,
    fx_rate_to_eur,
    amount_eur,
    _batch_id
FROM gold.finance_invoice_export;
