# Documentation

## Product and architecture

- [Project scope](PROJECT_SCOPE.md) — implemented slice, target state, and explicit non-goals.
- [Architecture](ARCHITECTURE.md) — system context, data flow, serving model, and recovery path.
- [Data model](DATA_MODEL.md) — current source/Silver grains and planned finance star schema.
- [Platform responsibilities](adr/ADR-001-platform-responsibilities.md) — why Databricks, Snowflake, and Power BI have different jobs.

## Finance and trust

- [KPI definitions](KPI_DEFINITIONS.md) — business definition, calculation, grain, fields, and edge behavior.
- [Data-quality rules](DATA_QUALITY_RULES.md) — stable reason codes, thresholds, quarantine, and refresh semantics.
- [Security and governance](SECURITY_AND_GOVERNANCE.md) — secrets, roles, evidence, and ownership.

## Delivery

- [Milestone 1 validation](MILESTONE_1_VALIDATION.md) — local gates, cloud status, Gold controls,
  and correction evidence.
- [Milestone 2 validation](MILESTONE_2_VALIDATION.md) — authenticated Snowflake deployment,
  idempotent load, exact reconciliation, live grants, and the remaining Desktop gate.
- [Databricks runbook](DATABRICKS_RUNBOOK.md) — authentication, bundle commands, Delta inspection,
  recovery, and teardown.
- [Future work](FUTURE_WORK.md) — explicit non-blocking limitations and remaining milestones.
- [Acceptance criteria](ACCEPTANCE_CRITERIA.md) — executable definition of done.
- [Demo scenario](DEMO_SCENARIO.md) — commands and interview walkthrough.
- [Backlog](BACKLOG.md) — vertical slices, dependencies, tests, and evidence.
- [Slice 001 engineering review](SLICE_001_REVIEW.md) — completed work, decisions, evidence, and open questions.
- [Independent Slice 001 review](REVIEW_LOG.md) — reproduced findings and remediation status.
- [Independent Slice 001.1 re-review](RE_REVIEW_SLICE_001_1.md) — preserved findings and
  Slice 001.2 remediation references.
- [Slice 001.1 remediation handoff](handoffs/CODEX_REMEDIATION_SLICE_001_1.md) — commits,
  verification, limitations, and re-review questions.
- [Slice 001.2 remediation plan](handoffs/CODEX_REMEDIATION_PLAN_001_2.md) — root causes,
  invariants, migration policy, and planned evidence.
- [Slice 001.2 remediation handoff](handoffs/CODEX_REMEDIATION_SLICE_001_2.md) — final commits,
  verification, limitations, and narrow re-review questions.

## Architecture decision records

- [ADR-001: Platform responsibilities](adr/ADR-001-platform-responsibilities.md)
- [ADR-002: Medallion architecture](adr/ADR-002-medallion-architecture.md)
- [ADR-003: Idempotent processing](adr/ADR-003-idempotent-processing.md)
- [ADR-004: Local and cloud adapters](adr/ADR-004-local-and-cloud-adapters.md)
- [ADR-005: Milestone 1 analytics and Delta](adr/ADR-005-milestone-1-analytics-and-delta.md)
