# Slice 001.1 Remediation Handoff

## Scope

Slice 001.1 repairs the local trust core reviewed at `40ac981`. It does not implement routes,
costs, Gold profitability, Databricks/Delta, Snowflake, or Power BI.

## Findings resolved

All BLOCKER and MAJOR findings LIB-R-001 through LIB-R-008 are closed with executable tests:

- finite, positive, unique FX references and finite non-negative financial values;
- cross-batch invoice claims with deterministic ownership and conflict withholding;
- committed-output readback reconciliation with fault-injection coverage;
- country, currency, customer, cost-center, and shipment reference enforcement;
- versioned replay identity and state-last crash recovery;
- one injectable storage protocol plus neutral domain contracts;
- short collision-checked Bronze path identifiers.

The remediation also closes minor findings for ambiguous input formats, distinct volume
counts, missing summaries, CSV formula injection, wheel portability, rounding documentation,
negative-path coverage, Windows paths, and workflow artifacts. Per-batch evidence grain and
valid-row publication from a quality-failed batch are explicit accepted policies.

## Architecture changes

Invoice claims are retained by batch and resolved across active state. Exact redelivery keeps
the earliest active owner; a conflicting payload withholds every claim until correction.
Silver and quarantine are read back after publication and reconciled against expected business
keys, batch contributions, evidence, and EUR totals. Run state is written only after data,
quality, reconciliation, and summary evidence, and replay identity includes pipeline, contract,
and quality-rule versions.

The local adapter remains single-writer with per-file atomic replacement. A future Delta
adapter must provide a serializable transaction or equivalent protocol spanning trusted data,
quarantine, quality evidence, and processed state.

## Commits

Commits after the reviewed baseline `40ac981`, in order:

```text
67ec3ec docs(review): record Slice 001 remediation plan
9c5cd56 refactor(contracts): centralize dataset and storage contracts
710b368 fix(paths): shorten immutable Bronze evidence paths
b14854d fix(validation): reject unsafe financial and reference values
c0bc5b2 fix(quality): detect conflicting FX reference records
6b262b9 fix(dedup): enforce cross-batch invoice uniqueness
9741a4e fix(reconciliation): verify committed storage readback
75b6b47 fix(replay): version processing state and commit it last
7a0bc1c fix(packaging): bundle runtime configuration defaults
f3ef26b fix(input): reject ambiguous formats and neutralize formulas
0db1034 test(contracts): prove independent storage adapter
ca70767 docs: publish Slice 001.1 trust contracts
```

The evidence-only commit that finalizes this file is identified by
`git log -- docs/handoffs/CODEX_REMEDIATION_SLICE_001_1.md`; a Git commit cannot embed its own hash.

## Verification results

Verified on Windows with Python 3.12.13:

```text
python -m pytest -q --cov=datalibra --cov-report=term-missing --cov-branch --cov-fail-under=90
82 passed in 48.34s
Total coverage: 96.91% (785 statements, 218 branches)

python -m ruff check .
All checks passed!

python -m ruff format --check .
39 files already formatted

python -m mypy src/datalibra
Success: no issues found in 21 source files

python -m pip check
No broken requirements found.

python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist
Successfully built datalibra-0.1.1-py3-none-any.whl
SHA-256: c3dd123c9c9b53d06ed859b97ea9304d241c440a88573aeb4cac1541f3d895ee
```

The wheel was installed with `--no-deps --target` in a neutral directory outside the checkout;
`python -m datalibra.cli generate healthy --output ./generated` completed successfully using the
packaged configuration defaults.

The CLI demo gate also passed:

```text
libra generate healthy ...       exit 0
libra run healthy ...            exit 0, success, 720 invoices, EUR 916351.47
libra generate broken ...        exit 0
libra run broken ...             exit 2 as designed
  duplicate_invoices             quality_failed, 720 trusted / 12 quarantined
  missing_gbp_fx                 quality_failed, 708 trusted / 12 quarantined
  incomplete_germany             quality_failed, 576 trusted / 43 quarantined
```

## Adversarial cases now passing

- zero, negative, NaN, infinity, malformed, missing, duplicate, and conflicting FX inputs;
- NaN, infinity, malformed, and forbidden negative monetary values;
- unknown country, currency, customer, cost-center, and shipment references;
- exact and conflicting invoice claims across batches, scoped correction, and replay order;
- storage adapters that drop half the rows, alter an amount, or omit a batch contribution;
- obsolete pipeline/contract/rules versions, missing summaries, and interrupted publication;
- deep Windows output roots and short-fingerprint collision detection;
- ambiguous regional dates/decimals and spreadsheet-formula payloads;
- a complete independent in-memory implementation of `PipelineStorage`.

## Known limitations and intentional deferrals

- No arbitrary FX plausibility band was added. Slice 001.1 enforces finite rates greater than
  zero; business-approved currency bands require an owner and dated policy.
- Quarantine and quality evidence retain per-batch audit grain. Steward KPIs should count
  distinct business keys when measuring distinct issues.
- Valid rows from a `quality_failed` batch are published, but the trusted refresh watermark does
  not advance. Consumers must use the refresh/state gate; transactional release is deferred to
  the Delta adapter.
- The static country-volume threshold remains a deterministic demo control. Historical and
  holiday-aware baselines remain future policy work.

## Questions for independent re-review

1. Do the cross-batch claim and correction tests establish the intended ownership semantics?
2. Does the committed-readback fault suite provide sufficient evidence for the local adapter?
3. Is the explicit valid-row publication policy acceptable until transactional Delta release?
4. Are any BLOCKER or MAJOR findings still reproducible?

## Recommendation

Do not begin Slice 002 until independent re-review confirms that LIB-R-001 through LIB-R-008
are closed.
