# Project Scope

## Product intent

Libra gives Northstar Logistics Group a traceable path from heterogeneous regional finance feeds to reliable management reporting. It emphasizes correctness, recovery, and explainability over platform breadth.

## MVP — Slice 001

- Deterministic 2025 synthetic data for Germany, Netherlands, France, United Kingdom, and Türkiye.
- Countries, currencies, daily exchange rates, customers, cost centers, shipments, invoices, and monthly budgets.
- Healthy, duplicate-invoice, missing-GBP-rate, and incomplete-Germany scenarios.
- Local Bronze and Silver storage with Spark-compatible transformation boundaries.
- Standard identifiers, ISO dates/codes, fixed-scale decimals, date-effective EUR conversion.
- Duplicate, required-field, missing-FX, referential-integrity, and volume-drop controls.
- Quarantine, quality results, reconciliation evidence, refresh state, and idempotent reprocessing.
- Unit, integration, contract, and executable demo tests.
- Databricks, Snowflake, and Power BI responsibilities/interfaces documented without claiming a deployment.

## Portfolio-ready version

- Real PySpark/Delta implementation deployed through Databricks Asset Bundles.
- Incremental file discovery and Delta `MERGE`, schema evolution policy, and operational cost/route data.
- Late-arriving invoice and retroactive correction demonstrations across accounting periods.
- Snowflake migrations for the finance star schema, governed marts, audits, and roles.
- A Power BI PBIP/TMDL project completed and visually verified in Power BI Desktop.
- CI with coverage, lint, type, contract, and small Spark integration tests.
- Observability runbook, retained job evidence, and measured performance envelope.

## Optional future improvements

- Additional regional source formats and fiscal calendars.
- Automated lineage export and catalog integration.
- Data retention/archival policies and cost controls.
- Deployment promotion and disaster-recovery exercises.

These are explicitly not in scope: Kubernetes, microservice decomposition, machine learning, forecasting, real carrier data, a fabricated PBIX binary, or duplicated business transformation logic in both Databricks and Snowflake.
