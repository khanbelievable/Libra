# Project Scope

## Product intent

Libra gives Northstar Logistics Group a traceable path from heterogeneous regional finance feeds to reliable management reporting. It emphasizes correctness, recovery, and explainability over platform breadth.

## Implemented — Milestone 1

- Deterministic 2025 synthetic data for Germany, Netherlands, France, United Kingdom, and Türkiye.
- Countries, currencies, daily exchange rates, customers, cost centers, routes, shipments,
  invoices, monthly budgets, and shipment-linked operational costs.
- Healthy, invoice/FX/volume/cost failure, and historical cost-correction scenarios.
- Local Bronze/Silver/Gold execution plus real PySpark transformations and Delta publication code.
- Standard identifiers, ISO dates/codes, fixed-scale decimals, date-effective EUR conversion.
- Duplicate, required-field, missing-FX, referential-integrity, and volume-drop controls.
- Quarantine, quality results, reconciliation evidence, refresh state, and idempotent reprocessing.
- Five deterministic Gold analytics contracts and direct route/customer cost allocation.
- Unit, integration, contract, executable demo, and local Spark parity tests.
- A deployable three-task Databricks bundle; authenticated workspace execution is not claimed
  until its pending manual validation is completed.
- Snowflake and Power BI remain interface specifications for Milestone 2.

## Remaining delivery

- Complete the authenticated Databricks deploy/run and retain safe Delta inspection evidence.
- Snowflake migrations for the finance star schema, governed marts, audits, and roles.
- A Power BI PBIP/TMDL project completed and visually verified in Power BI Desktop.
- Observability runbook, retained job evidence, and measured performance envelope.

## Optional future improvements

- Additional regional source formats and fiscal calendars.
- Automated lineage export and catalog integration.
- Data retention/archival policies and cost controls.
- Deployment promotion and disaster-recovery exercises.

These are explicitly not in scope: Kubernetes, microservice decomposition, machine learning, forecasting, real carrier data, a fabricated PBIX binary, or duplicated business transformation logic in both Databricks and Snowflake.
