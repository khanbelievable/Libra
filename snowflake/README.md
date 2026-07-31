# Snowflake governed serving

This directory contains the executable Milestone 2 serving layer. Snowflake receives only
approved Databricks extracts; it does not cleanse source rows, resolve duplicates, or reinterpret
FX policy.

## Layout

```text
bootstrap/001_platform.sql              roles, database, schemas, migration ledger
migrations/001_control_and_load.sql     audit, staging tables, file format, internal stage
migrations/002_finance_star.sql         six dimensions, five facts, idempotent publication
migrations/003_reporting_views.sql      model, mart, status, and drill-through views
migrations/004_security_and_controls.sql least-privilege reader/loader grants
tests/reconciliation.sql                independent blocking finance controls
packages/                               ignored local governed extracts
```

The Python adapter discovers migrations in strict numeric order and rejects checksum drift.
Packages must contain exactly the ten versioned source tables plus `manifest.json`. The loader
verifies every checksum, row count, and financial total before it connects.

An unchanged successful `SOURCE_FINGERPRINT` returns `UNCHANGED`. A new package is copied to an
immutable load-specific stage path and published through natural-key `MERGE` statements. The
stored procedure records target counts/totals and six oracle controls; any non-successful
procedure result rolls back and marks the load failed.

## Authentication and deployment

Credentials belong in a named Snowflake connector connection, never this repository. The
connector searches the standard Windows location:

```text
%USERPROFILE%\AppData\Local\snowflake\connections.toml
```

Example commands after a safe named connection exists:

```powershell
libra_snowflake --connection libra smoke
```

Run `bootstrap/001_platform.sql` once with delegated role-management privileges. It creates only
the portfolio-sized database/roles/schemas; it deliberately does not create a warehouse. Grant
`USAGE` on an existing approved warehouse to the deployment, loader, and reader roles as required.
Then:

```powershell
libra_snowflake --connection libra migrate
libra_databricks_export --databricks <path-to-cli> --profile LIBRA `
  --warehouse-id <existing-id> --catalog workspace --schema libra `
  --output snowflake/packages/m2-approved --load-id <immutable-load-id>
libra_snowflake validate-package snowflake/packages/m2-approved
libra_snowflake --connection libra load snowflake/packages/m2-approved
```

Run `tests/reconciliation.sql`, rerun the unchanged package, and inspect grants before declaring
deployment complete. The expected values are 720 invoices, 2,880 costs, EUR 916,351.47 revenue,
EUR 230,279.65 cost, EUR 686,071.82 gross profit, and EUR 3,048,056.60 budget.

The authenticated Milestone 2 deployment, governed load, unchanged second run, live grants, and
zero-difference controls are recorded in `docs/MILESTONE_2_VALIDATION.md`. That evidence contains
no connection configuration, account URL, identity, credential, token, or raw package content.
