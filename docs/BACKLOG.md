# Backlog

Status values: `DONE`, `IN PROGRESS`, `PLANNED`.

## Final delivery milestones

1. **Milestone 1 — Business analytics + real Databricks execution:** DONE, including
   authenticated bundle deployment, successful execution, Delta inspection, zero-difference
   parity, and correction evidence.
2. **Milestone 2 — Snowflake + Power BI:** IN PROGRESS. Executable migrations, governed export
   and loader, authenticated Snowflake deployment/load/idempotency/reconciliation, and a
   schema-valid PBIP/TMDL/PBIR project are complete. Power BI Desktop refresh, DAX execution,
   interaction checks, and visual review remain the final manual gate.
3. **Milestone 3 — Final packaging and release:** PLANNED.

The older LIBRA items below retain design history; Milestone 1 combines the relevant parts of
LIBRA-002, a focused LIBRA-003 demonstration, and LIBRA-004.

## LIBRA-001 — Trusted EUR invoice slice

- **Goal:** Generate 12 months of source data and process healthy/failure batches from Bronze to Silver with quarantine.
- **Business value:** Demonstrates that management revenue cannot be inflated by resends, incomplete deliveries, or missing FX.
- **Components affected:** generator, local ingestion/storage, domain transforms, quality, reconciliation, CLI, tests, docs.
- **Acceptance criteria:** All Slice 001 criteria in `docs/ACCEPTANCE_CRITERIA.md`.
- **Required tests:** unit normalization/FX/rules; integration pipeline/idempotency; schema contracts; four demo scenarios.
- **Demo evidence:** generated manifests, Silver/quarantine files, quality CSV, reconciliation JSON, pytest output.
- **Dependencies:** Python 3.12; no cloud credentials.
- **Completion status:** DONE (Slice 001; evidence in `docs/SLICE_001_REVIEW.md`).

## LIBRA-001.1 — Trust core remediation

- **Goal:** Close the independent review's trust failures without expanding product scope.
- **Business value:** Makes FX conversion, invoice ownership, replay state, and reconciliation
  defensible under adversarial input and storage faults.
- **Components affected:** contracts, local storage, validation, deduplication, reconciliation,
  replay state, packaging, tests, and audit documentation.
- **Acceptance criteria:** Slice 001 criteria plus the remediation additions in
  `docs/ACCEPTANCE_CRITERIA.md`.
- **Required tests:** financial/FX boundaries, reference integrity, cross-batch ownership,
  committed-write corruption, version mismatch, interrupted replay, path length, and wheel smoke.
- **Demo evidence:** full automated suite, four CLI scenarios, coverage report, and
  `docs/handoffs/CODEX_REMEDIATION_SLICE_001_1.md`.
- **Dependencies:** LIBRA-001 and independent review at `40ac981`.
- **Completion status:** DONE; independent re-review completed with changes required. Findings
  are recorded in `docs/RE_REVIEW_SLICE_001_1.md`.

## LIBRA-001.2 — Claims integrity remediation

- **Goal:** Close the Slice 001.1 re-review findings without expanding the product boundary.
- **Business value:** Makes financial ownership stable, independently attests durable claims and
  committed run evidence, and proves deterministic crash recovery.
- **Components affected:** claims, replay state, local storage, reconciliation, CSV boundaries,
  non-invoice ownership policy, tests, ADRs, and handoff evidence.
- **Acceptance criteria:** Slice 001 criteria plus the claims-integrity additions in
  `docs/ACCEPTANCE_CRITERIA.md`.
- **Required tests:** arrival-order permutations, financial-identity conflicts, manifest and
  aggregate corruption, no-op artifact corruption, fault-injected publication recovery,
  canonical CSV round trips, non-invoice collisions, determinism, paths, and wheel smoke.
- **Demo evidence:** full automated suite, CLI healthy/broken runs, branch coverage, wheel install,
  and `docs/handoffs/CODEX_REMEDIATION_SLICE_001_2.md`.
- **Dependencies:** LIBRA-001.1 and independent re-review at `54748ff`.
- **Completion status:** DONE; awaiting narrow independent re-review before Slice 002 starts.

## LIBRA-002 — Operational cost and route profitability

- **Goal:** Add routes, fuel/labor/warehousing/transport costs, and route/customer profitability Gold aggregates.
- **Business value:** Explains margin drivers beyond top-line revenue.
- **Components affected:** generator, Silver, Gold, quality, data model, KPI tests.
- **Acceptance criteria:** Cost transactions reconcile; route/customer gross profit is reproducible; invalid references are quarantined.
- **Required tests:** cost allocation, negative/credit handling, route joins, aggregate reconciliation.
- **Demo evidence:** route and customer profitability extracts.
- **Dependencies:** LIBRA-001.2 and reviewer approval to proceed.
- **Completion status:** DONE in Milestone 1 local and Spark implementations.

## LIBRA-003 — Late arrival and correction lifecycle

- **Goal:** Add late invoices and retroactive corrections with accounting-period impact evidence.
- **Business value:** Proves safe recovery without duplicate revenue or silent historical drift.
- **Components affected:** generator, merge/state, reconciliation, audit, runbook.
- **Acceptance criteria:** Late record updates the intended month; correction replaces prior values; lineage identifies both versions.
- **Required tests:** replay, changed fingerprint, period restatement, unchanged re-run.
- **Demo evidence:** before/after monthly totals and correction audit.
- **Dependencies:** LIBRA-001.
- **Completion status:** Focused cost-correction demonstration DONE in Milestone 1; a generalized
  accounting-restatement lifecycle remains future work.

## LIBRA-004 — Databricks/Delta production adapter

- **Goal:** Implement Auto Loader/batch ingestion, Delta Bronze/Silver/Gold, expectations, and Asset Bundle deployment.
- **Business value:** Demonstrates production-scale incremental processing and operations.
- **Components affected:** Databricks notebooks/jobs/bundles, Spark adapter, CI contracts.
- **Acceptance criteria:** Same fixtures match local contract; Delta merges are idempotent; deployment validates in a workspace.
- **Required tests:** local Spark tests and cloud smoke/job tests.
- **Demo evidence:** bundle validation, job run, Delta history.
- **Dependencies:** LIBRA-001 through LIBRA-003.
- **Completion status:** DONE; authenticated evidence is in `docs/MILESTONE_1_VALIDATION.md`.

## LIBRA-005 — Snowflake governed serving layer

- **Goal:** Deploy conformed finance star schema, marts, reconciliation tables, and least-privilege roles.
- **Business value:** Provides stable, governed consumption contracts.
- **Components affected:** migrations, tables, views, marts, security, load adapter.
- **Acceptance criteria:** Incremental load reconciles; roles restrict access; marts meet semantic contract.
- **Required tests:** SQL schema, grant, uniqueness, reconciliation, and query tests.
- **Demo evidence:** migration log, grants, sample mart results.
- **Dependencies:** LIBRA-002, LIBRA-004.
- **Completion status:** IN PROGRESS; implementation and local contract tests are complete,
  authenticated deployment/load/grant evidence is pending.

## LIBRA-006 — Power BI semantic/report experience

- **Goal:** Complete PBIP/TMDL relationships, DAX, seven report pages, drill-through, and visual QA.
- **Business value:** Makes trusted finance results actionable for management and data stewards.
- **Components affected:** semantic model, report, DAX, Power BI documentation.
- **Acceptance criteria:** Measures match SQL controls; pages meet specs; freshness/DQ visible; drill-through works.
- **Required tests:** relationship validation, DAX control totals, refresh test, visual checklist.
- **Demo evidence:** PBIP source, screenshots, recorded measure reconciliation.
- **Dependencies:** LIBRA-005.
- **Completion status:** IN PROGRESS; real source artifacts, 12 tables, 22 relationships,
  14 measures, seven pages, and data-bound visuals are present and PBIR schema validation passes.
  Desktop refresh, DAX execution, interaction checks, and screenshots remain pending.
