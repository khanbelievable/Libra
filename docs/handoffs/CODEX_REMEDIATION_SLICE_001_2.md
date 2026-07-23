# Slice 001.2 Claims Integrity Remediation Handoff

## Scope and reviewed baseline

Slice 001.2 starts from
`54748ff01f07ad1e33c859bd11fced3ad189fffa`, the Slice 001.1 evidence commit independently
re-reviewed in `docs/RE_REVIEW_SLICE_001_1.md`. It closes the two new MAJOR findings and their
direct integrity residuals. It does not implement Slice 002, routes, operational costs, Gold,
Databricks/Delta, Snowflake, or Power BI.

The design was committed before production changes in
`docs/handoffs/CODEX_REMEDIATION_PLAN_001_2.md`. Historical re-review evidence remains intact.

## Commits

Commits after the reviewed baseline, in order:

```text
b3164d6 docs(review): plan Slice 001.2 claims integrity remediation
1e0410b refactor(state): persist stable batch arrival sequence
405820b fix(claims): fingerprint normalized financial identity
f5463f2 fix(claims): attest batch-owned contributions
cfa3ba2 fix(replay): attest committed run evidence
b4fd01c fix(storage): preserve canonical internal CSV values
5b70b8a fix(ownership): reject unsupported financial fact conflicts
a406bae test(paths): make Windows path guard portable
a473869 fix(recovery): converge interrupted attested publication
3b90485 test(integrity): pin deterministic outputs and altered evidence recovery
303e98a docs: publish Slice 001.2 integrity contracts
```

The evidence-only commit that finalizes this file is identified by
`git log -- docs/handoffs/CODEX_REMEDIATION_SLICE_001_2.md`; a commit cannot contain its own hash.

## LIB-RR-001 resolution

Processed state now assigns every accepted batch a positive, unique `arrival_sequence`. New
sequences are `max(existing) + 1` under the documented local single-writer model. Correction,
reprocessing, sorted JSON, and unrelated arrivals do not change an existing sequence.

Invoice resolution sorts by `(arrival_sequence, batch_id, source_row_number)`. `batch_id` is a
stable corruption/legacy tie-breaker only; it is not the normal ownership rank. Regression tests
cover non-alphabetical arrivals, sorted state JSON, an unrelated third batch, correction, both
processing-order permutations, unchanged revenue, and byte-stable trusted output.

Invoice business identity remains `invoice_id`. The financial claim fingerprint is a SHA-256 over
normalized invoice ID, shipment ID, invoice/translation date, country, customer, cost center,
source currency and amount, applied FX rate, and translated EUR amount. Formatting-only
differences normalize to an exact replay. A different applied rate or EUR result is a conflict,
and every active conflicting occurrence is withheld regardless of arrival order.

## LIB-RR-002 resolution

`claims/invoices/<batch_id>.csv` is the authoritative batch-owned contribution. Each active state
record independently attests:

- claim count;
- deterministic full-row digest;
- invoice business-key digest;
- source fingerprint;
- pipeline, data-contract, and quality-rules versions;
- immutable arrival sequence.

Before resolution, the pipeline verifies every active manifest against state. It rebuilds
`claims/invoices.csv` only from verified manifests and verifies that aggregate before use. The
aggregate is therefore a disposable index, never the sole source for both expected and actual
results.

Missing, empty, truncated, altered, mis-owned, or duplicated batch evidence raises a typed claims
integrity error before trusted publication or state advancement. A deleted, empty, truncated,
altered, duplicated, or stale aggregate is detected and safely reconstructed from attested
manifests. Missing processed-state attestation is rejected. Tests assert that the original 720
trusted invoices and prior state remain unchanged on fail-closed paths.

## Related residuals resolved

- **LIB-RR-003:** the path test measures the longest actual committed path plus atomic `.tmp`
  suffix against an explicit practical Windows limit.
- **LIB-RR-004/005:** state attests Silver, expected quarantine, quality rows, reconciliation JSON,
  and summary JSON. No-op verifies them all. Missing or altered current-batch evidence triggers
  deterministic reprocessing; damaged evidence owned by another active batch fails closed.
  An absent quarantine file is valid only when its attested row count is zero.
- **LIB-RR-006:** internal CSVs retain canonical values. Spreadsheet formula neutralization is an
  explicit export-only operation and its output cannot re-enter claims or reconciliation.
- **LIB-RR-007:** exact shipment and budget replays preserve the first owner and emit noncritical
  `CROSS_BATCH_RECORD_OWNERSHIP` evidence. Conflicting normalized financial payloads fail before
  overwrite with `CrossBatchCollisionError`.
- **LIB-RR-008:** malformed state raises `StateIntegrityError` naming the state file and ordered
  replay recovery policy.
- **LIB-RR-009:** future transactional scope now explicitly includes claims, Silver, quarantine,
  quality, reconciliation, summary, and state.
- **LIB-RR-010:** the planned PBIP project name is `Libra`.

## Existing-state migration

A Slice 001.1 workspace with one unsequenced batch can migrate only by replaying that same source.
Sequence `1` is then unambiguous, and the replay recreates and attests its claims and committed
evidence.

A workspace with multiple unsequenced batches is rejected with `STATE_MIGRATION_REQUIRED`.
Operators must archive or clear processed outputs and replay the original sources in true arrival
order. An unrelated batch cannot trigger migration. Lexical batch IDs, JSON order, timestamps,
filenames, and filesystem order are deliberately not accepted as substitutes for historical
arrival evidence.

## Atomicity and recovery

The local adapter remains single-writer and uses atomic per-file replacement. Publication order
is:

1. load state and verify unrelated active attestations;
2. persist immutable Bronze evidence;
3. persist an inflight marker for the exact batch and fingerprint;
4. publish and read back the batch claim manifest;
5. rebuild and verify the aggregate claim index;
6. publish Silver and quarantine;
7. read committed data and reconcile;
8. publish and verify quality evidence;
9. publish and verify reconciliation JSON;
10. publish and verify the run summary;
11. write processed state last and clear the inflight marker.

The inflight marker is recovery metadata, never success state. Only an exact retry of its batch and
fingerprint may recover through current-batch mismatches. Fault injection after the claim
manifest, claim aggregate, invoice Silver, quality, reconciliation, and summary boundaries proves
that retry converges to 1,440 unique invoices for two disjoint batches, preserves sequences `1`
and `2`, retains the unrelated contribution, and removes the marker.

## Verification

Verified on Windows with Python 3.12.13:

```text
python -m pytest -q --cov=datalibra --cov-report=term --cov-branch --cov-fail-under=90
139 passed in 196.94s
Total coverage: 95.40% (978 statements, 282 branches)

python -m ruff check .
All checks passed!

python -m ruff format --check .
45 files already formatted

python -m mypy --strict src/datalibra
Success: no issues found in 23 source files

python -m pip check
No broken requirements found.
```

The committed source inputs were staged outside the checkout and built without network or build
isolation:

```text
python -m pip wheel --no-deps --no-build-isolation --wheel-dir <external>/dist <external>/source
Successfully built datalibra-0.1.2-py3-none-any.whl
SHA-256: 107f058931efbc59f64e9a318a37c83b70cb4a426a0f2f6ad6eed80927367a79
```

The wheel was installed into a fresh external virtual environment. The generated `libra`
entry point ran outside the checkout, reported package version `0.1.2`, and loaded both packaged
dataset and quality-rule configuration directories.

Packaged CLI evidence:

```text
libra generate healthy ...       exit 0
libra run healthy ...            exit 0, success, 720 invoices, EUR 916351.47
libra run healthy ...            exit 0, already_processed, unchanged totals
libra generate broken ...        exit 0
libra run-batch duplicate_invoices ...
                                 exit 2, 720 trusted / 12 quarantined
libra run-batch missing_gbp_fx ...
                                 exit 2, 708 trusted / 12 quarantined
libra run-batch incomplete_germany ...
                                 exit 2, 576 trusted / 43 quarantined
```

Targeted integrity evidence:

```text
pytest cross-batch, claim-integrity, no-op-integrity, publication-recovery,
       replay-state, CSV, non-invoice, and deterministic-output tests
64 passed in 72.74s

pytest test_deep_output_root_stays_below_practical_windows_path_limit
       --basetemp <nested temporary root>
1 passed in 0.92s
```

The adversarial suites explicitly cover:

1. non-alphabetical arrival and JSON key sorting;
2. an unrelated third batch preserving owner and bytes;
3. applied-rate and EUR-result conflicts in both orders;
4. deleted/empty/truncated/altered/duplicated/stale aggregate claims;
5. missing/truncated/altered/mis-owned/duplicated batch manifests;
6. missing or altered no-op evidence for every attested artifact;
7. correction with an unchanged arrival sequence;
8. reconciliation expectations derived independently of the aggregate index;
9. byte-identical independent output trees;
10. interruption and exact-retry convergence at every attested publication boundary.

## Intentional deferrals and known limitations

- Invoice is the only dataset with full cross-batch claim resolution. Shipment and budget
  collisions have the bounded fail-closed policy above. Dimension and FX reference ownership does
  not yet have generalized claims; that requires a separately reviewed architecture.
- The local adapter is single-writer and not a distributed transaction system. Its per-file
  atomic replacements, inflight marker, readback attestations, and state-last protocol provide
  deterministic local recovery. A production Delta adapter must implement the documented
  transaction scope.
- A multi-batch Slice 001.1 workspace cannot be assigned truthful historical order automatically;
  ordered replay is required.
- Valid rows from a `quality_failed` batch remain published, but the trusted refresh watermark
  does not advance. Local consumers must honor processed state.
- Historical baselines, finance-owned FX plausibility bands, and cloud deployment remain outside
  Slice 001.2.

## Narrow re-review questions

1. Can any dictionary, JSON, batch-ID, filename, timestamp, or filesystem ordering still change
   normal invoice ownership?
2. Can damaged batch claims or the aggregate index still remove trusted Silver without an
   integrity failure or attested rebuild?
3. Does the enriched normalized financial fingerprint distinguish every value that changes the
   trusted EUR result?
4. Can any missing or altered committed artifact produce a false `already_processed` response?
5. Does exact retry converge safely at each tested local publication boundary?
6. Is any BLOCKER or MAJOR finding still reproducible within Slice 001.2?

## Recommendation

Slice 001.2 is ready for a narrow independent re-review. Do not begin Slice 002 until that review
confirms the claims-integrity findings are closed.
