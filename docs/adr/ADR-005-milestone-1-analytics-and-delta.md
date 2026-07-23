# ADR-005: Milestone 1 analytics and Delta execution

- **Status:** Accepted
- **Decision:** Add route and operational-cost facts to the existing batch model, allocate every
  cost directly through shipment, compare FX to the first available same-currency rate in each
  calendar month, and publish exactly five Gold contracts. Keep the local implementation as the
  deterministic oracle and implement Databricks as one three-task PySpark/Delta bundle.
- **Context:** Management needs explainable route/customer profit and budget variance, while a
  portfolio implementation must prove a real cloud execution path without duplicating finance
  rules in the future serving layer.
- **Consequences:** Direct allocation reconciles exactly but does not model shared corporate cost.
  Percentages use reconciled totals and four decimal places. Databricks Bronze is idempotent by
  batch/fingerprint/source row; references merge globally by natural key; facts replace one batch
  contribution transactionally. A financial key owned by another cloud batch fails closed rather
  than creating duplicate totals. Local Spark contracts must match local Gold controls.
