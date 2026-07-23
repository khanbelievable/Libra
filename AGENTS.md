# Engineering Guide

Libra is delivered as reviewable vertical slices. Keep changes inside the active backlog
item and leave the repository runnable after each commit.

## Working agreement

- Read the active acceptance criteria, architecture, quality rules, ADRs, and handoff before
  changing behavior.
- Treat finance arithmetic, reason codes, business keys, state identity, and publication
  ordering as contracts. Record material changes in tests and documentation.
- Preserve immutable Bronze evidence. Invalid or disputed financial records must not enter
  trusted Silver.
- Preserve immutable arrival sequence and batch-owned claim manifests. The aggregate claims CSV
  is a verified rebuildable index, never an independent authority.
- Treat claim and committed-artifact attestations as replay preconditions. Processed state is
  written last; an inflight marker supports recovery but never represents success.
- Preserve canonical values in internal CSVs. Spreadsheet neutralization is permitted only at an
  explicit export boundary whose output cannot re-enter processing.
- Keep the local adapter dependency-free and single-writer. Cloud adapters are separate
  backlog work and must not be represented as deployed before executable evidence exists.
- Use Conventional Commits and keep each commit logically complete.

## Required verification

```text
python -m pytest -q --cov=datalibra --cov-report=term --cov-branch --cov-fail-under=90
python -m ruff check .
python -m ruff format --check .
python -m mypy src/datalibra
python -m pip check
```

For a release-oriented change, also build the wheel and smoke-test the installed CLI from a
directory outside the checkout. Generated data, credentials, local editor settings, and
processing output are never committed.
