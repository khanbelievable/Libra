# Role Model

- `LIBRA_LOADER`: insert/merge into controlled load tables and load audit; no reporting grants.
- `LIBRA_OWNER`: owns schema objects through deployment automation; not assigned to interactive analysts.
- `LIBRA_FINANCE_READER`: selects approved finance reporting views.
- `LIBRA_DQ_READER`: selects quality, quarantine summary, freshness, and reconciliation views.
- Power BI service identity receives the two reader roles required by its workspace, never owner/loader.

Actual grants are defined in `migrations/004_security_and_controls.sql` and contract-tested.
Warehouse `USAGE` is deliberately environment-specific and must be granted only on the existing
warehouse selected for deployment.
