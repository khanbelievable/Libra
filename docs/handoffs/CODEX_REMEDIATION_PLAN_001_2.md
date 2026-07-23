# Slice 001.2 Claims Integrity Remediation Plan

- **Starting commit:** `54748ff01f07ad1e33c859bd11fced3ad189fffa`
- **Independent re-review:** `docs/RE_REVIEW_SLICE_001_1.md` and
  `docs/handoffs/CLAUDE_RE_REVIEW_SLICE_001_1.md`
- **Scope:** claims integrity and directly related replay, evidence, storage, portability, and
  documentation defects only. Slice 002 and every cloud/serving feature remain out of scope.

## Root causes

### LIB-RR-001 — unstable owner rank and incomplete financial identity

Two defects combine:

1. `_resolve_invoice_claims` receives `list(state["batches"])` as owner rank. Local JSON writes
   use `sort_keys=True`, so the persisted dictionary is read back in lexical batch-ID order.
   Python insertion order is therefore being used as unstated business state even though that
   order is not preserved by the storage format. A later unrelated run reloads the sorted state,
   re-resolves every claim, and can replace the true first arrival with an alphabetically earlier
   batch.
2. `canonical_invoice_payload` excludes `fx_rate_to_eur` and `amount_eur`. Two normalized invoice
   claims that produce different EUR values can compare equal, be treated as an exact replay, and
   become financially interchangeable when ownership rank changes.

Affected source:

- `src/datalibra/silver/pipeline.py`: no-op/state handling, active-owner ordering, claim resolution.
- `src/datalibra/domain/contracts.py`: canonical invoice claim definition.
- `src/datalibra/storage/local.py`: sorted JSON exposes the implicit-order defect but is not itself
  wrong; state must not depend on JSON member order.
- `src/datalibra/domain/models.py`: summaries may expose the persisted sequence for evidence.

Affected artifacts:

- `state/processed_batches.json`
- `claims/invoices.csv`
- `silver/invoices.csv`
- `quarantine/invoices.csv`
- historical summaries and reconciliation evidence whose contribution can become stale after a
  silent owner flip.

### LIB-RR-002 — unattested aggregate claims system of record

`claims/invoices.csv` is both the only persisted input to global invoice resolution and the source
from which the pipeline derives its expected Silver result. If it is deleted, truncated, altered,
or stale, the pipeline resolves a smaller or changed claim set, overwrites all invoice Silver from
that set, and then reconciles the committed result against the same damaged input. Expected and
actual agree while previously trusted revenue disappears.

Affected source:

- `src/datalibra/storage/base.py`: no batch-owned claim-manifest or evidence-read contract.
- `src/datalibra/storage/local.py`: one mutable aggregate claim file with no independent manifest.
- `src/datalibra/silver/pipeline.py`: claim publication precedes verification; expected Silver is
  derived from the aggregate; no-op checks only state versions and summary readability.

Affected artifacts:

- `claims/invoices.csv` (aggregate index)
- new `claims/invoices/<batch_id>.csv` batch-owned contribution manifests
- `state/processed_batches.json` claim and artifact attestations
- `silver/*.csv`, `quarantine/*.csv`, `quality/quality_results.csv`,
  `reconciliation/<batch_id>.json`, and `runs/<batch_id>.json`

## Chosen design

Use design A: a current batch-owned invoice-claim manifest is the durable contribution for each
active batch. State independently attests each manifest with:

- expected claim count;
- deterministic full-row claim digest;
- deterministic invoice business-key digest;
- source fingerprint;
- pipeline, data-contract, and quality-rules versions;
- immutable monotonic `arrival_sequence`.

`claims/invoices.csv` remains a convenient aggregate index, but it is rebuilt only from verified
batch manifests and verified again before resolution. It is never the sole source for both
expected and actual results.

Canonical financial claim identity is a SHA-256 over normalized:

- invoice ID;
- shipment ID;
- invoice/translation date;
- country, customer, and cost-center IDs;
- source currency and normalized source amount;
- applied FX rate value (whose date/currency identity is already included);
- translated EUR amount.

`source_updated_at`, CSV quoting, whitespace discarded by identifier/code normalization, decimal
spelling, and file order do not define financial equality.

## Required invariants

1. Every valid active batch has one positive, unique, immutable `arrival_sequence`.
2. A correction or compatible rebuild reuses its batch's sequence.
3. New sequences are assigned as `max(existing) + 1` under the documented local single-writer
   model. Claim sorting is `(arrival_sequence, batch_id, source_row_number)`; `batch_id` is only a
   deterministic corruption/legacy tie-breaker, never normal rank.
4. Exact replay requires an identical normalized financial-claim fingerprint. A changed FX basis
   or EUR amount is a conflict and withholds all active occurrences.
5. Every active state's claim attestation matches its batch-owned manifest before aggregate
   resolution. A missing, extra, altered, duplicated, or owner-mutated row fails closed.
6. The aggregate claim index equals the union of verified active batch manifests plus the current
   candidate contribution before it can drive Silver.
7. A claims-integrity failure cannot rewrite Silver, advance a watermark, or write success state.
8. Before `already_processed`, committed Silver contribution, claim manifest/index, summary,
   reconciliation, quality rows, and expected quarantine contribution match state attestations.
   Empty quarantine need not have a physical file when its attested count is zero.
9. Publication order is: verify prior state/evidence; publish Bronze; validate; publish and verify
   batch claim manifest; rebuild and verify aggregate claims; resolve; publish Silver/quarantine;
   read back and reconcile; publish and verify quality; publish and verify reconciliation; publish
   and verify summary; write all updated attestations and state last.
10. Internal CSV persistence preserves canonical strings exactly. Spreadsheet neutralization is
    available only through an explicit export helper and never feeds reconciliation or ownership.
11. Conflicting cross-batch monetary/reference rows outside invoices cannot silently overwrite a
    prior owner. Exact normalized repeats may retain the existing owner; unsupported conflicting
    ownership is rejected explicitly. The documentation will not claim generalized claim
    resolution beyond invoices.

## Legacy-state and crash recovery

Slice 001.1 state has neither arrival sequence nor independent claim/artifact attestations.

- A workspace with exactly one legacy batch may be migrated only while replaying that same source
  batch. Sequence `1` is unambiguous; current input recreates and attests its batch manifest and
  all evidence.
- A workspace with multiple unsequenced legacy batches is rejected with an explicit instruction to
  archive/clear processed outputs and replay source batches in their true arrival order. Lexical
  batch ID, JSON order, timestamps, filenames, and filesystem order are not accepted substitutes.
- An unrelated new batch cannot silently migrate legacy state.
- If a correction crashes after replacing its batch manifest but before state, retry may recreate
  the current batch from the supplied source when its incoming fingerprint differs from prior
  state. All unrelated active manifests must still pass their old attestations.
- Orphan current-batch files from an interrupted, uncommitted first run are overwritten
  deterministically. State remains the active-batch authority and is written last.

This deliberately favors an explicit recovery instruction over inventing a false historical
arrival order.

## Smaller residuals

- Replace the brittle deep-path setup with a relative path-budget assertion over actual files and
  a platform-explicit practical Windows limit.
- Remove spreadsheet escaping from internal Silver/claims/quarantine/quality writes; test an
  explicit presentation export with dangerous prefixes and CSV quoting/Unicode cases.
- Attest quality, quarantine, reconciliation, and summary evidence and validate it on no-op.
- Wrap malformed state JSON with the state path and recovery instruction.
- Clarify non-invoice cross-batch ownership. Invoice is the only full claim-resolution mechanism;
  exact non-invoice repeats retain the existing owner and conflicting collisions fail closed in
  this slice rather than receiving a second claims architecture.
- Add reconciliation and summary evidence to the future transactional scope wording.
- Replace the stale `DataLibraFinance` planned PBIP name with `Libra`.

## Planned commits

1. `docs(review): plan Slice 001.2 claims integrity remediation`
   - retain the independent re-review, ignore `.venv*`, and commit this plan before production.
2. `refactor(state): persist stable batch arrival sequence`
   - explicit assignment, correction stability, legacy handling, non-alphabetical/third-batch
     tests.
3. `fix(claims): fingerprint normalized financial identity`
   - enriched claim digest and exact-versus-conflicting FX/formatting tests.
4. `fix(claims): attest batch-owned contributions`
   - batch manifests, state attestations, aggregate rebuild/verification, corruption matrix, and
     interruption recovery.
5. `fix(replay): attest committed run evidence`
   - Silver/quarantine/quality/reconciliation/summary attestations and no-op missing-artifact
     recovery tests.
6. `fix(storage): preserve canonical internal CSV values`
   - explicit spreadsheet export boundary and special-identifier/CSV round-trip tests.
7. `fix(ownership): reject unsupported cross-batch record conflicts`
   - exact-repeat first-owner behavior and fail-closed conflicting non-invoice facts/references.
8. `test(paths): make Windows path guard portable`
   - actual generated-path budget test with explicit assumptions.
9. `docs: publish Slice 001.2 claims integrity contracts`
   - update re-review status, architecture, model, quality, acceptance, backlog, ADRs, naming, and
     final handoff with exact evidence.

Commit grouping may be reduced where protocol and orchestration changes cannot leave a valid
intermediate state, but every commit will remain coherent and executable.
