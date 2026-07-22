# Security and Governance

Libra uses synthetic data only. Customer names and identifiers are fictional and deterministic. Generated datasets are not committed.

## Controls

- Secrets enter cloud adapters through environment variables locally and managed secret stores in deployed environments.
- `.env` is ignored; `.env.example` contains names but no values.
- Databricks service principals receive write access only to their catalog/schema paths.
- Snowflake separates loader, transformer/owner, finance-reader, and data-quality-reader roles.
- Power BI users consume governed views; workspace authors do not receive warehouse ownership.
- Batch manifests, quality outcomes, reconciliation evidence, and correction lineage form the audit trail.
- Quarantine access is more restrictive than aggregate reporting because future source records may contain business identifiers.

## Data lifecycle

Production retention, deletion, legal hold, and regional residency periods require owner approval before deployment. Slice 001 writes local evidence only and provides no external transfer.

## Governance ownership

Finance owns KPI definitions and accounting policies; data engineering owns pipeline implementation; data stewards own source-quality remediation; platform/security teams own identities, network controls, and secret stores. Schema and KPI changes require contract/test updates and reviewer approval.
