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

The final commit list and exact verification output are completed after the documentation gate.

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
