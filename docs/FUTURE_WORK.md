# Future Work

This file records non-blocking work that is intentionally outside Milestone 1.

## Databricks parity and operations

- The Delta adapter fails closed when another batch owns the same financial natural key. The
  local oracle supports richer invoice exact-replay/conflict withholding through attested claim
  manifests. A future cloud hardening pass may implement the same claim-manifest lifecycle in
  Delta; until then the guard favors correct totals over availability.
- Delta provides atomicity per table, while the three job tasks provide ordered convergence across
  tables. A multi-table transaction ledger and automated rollback orchestration are not required
  for this portfolio-sized batch implementation.
- Production observability, alert routing, retention, table optimization, and cost controls need
  workspace-specific owners and policies.
- The deterministic country-volume threshold remains a demo control. A production threshold
  requires historical baselines, holiday calendars, and steward-approved overrides.

## Finance policy

- FX impact uses the first available rate in each calendar month as the comparison rate. Finance
  should approve or replace that baseline before production use.
- Every generated operational cost is directly shipment-linked, so route and customer allocation
  is exact. Shared corporate costs and allocation drivers remain out of scope.
- Credit notes, negative allowed cost adjustments, tax, and accounting-period close rules require
  explicit finance policy before implementation.

## Platform roadmap

- Milestone 2 implements Snowflake governed serving and Power BI. Existing files in those
  directories are interface specifications only.
- Milestone 3 covers final packaging, public release evidence, repository polish, and operational
  release checks.
