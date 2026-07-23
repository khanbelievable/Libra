# Independent Re-Review — Slice 001.1 Trust Core Remediation

- **Reviewer:** Claude (independent senior data-engineering review)
- **Date:** 2026-07-22
- **Baseline previously reviewed:** `40ac981`
- **Commit re-reviewed:** `54748ff` (`main`, clean working tree)
- **Environment:** Windows 11, Python 3.12.10, fresh `.venv-rereview`, editable install; separate
  clean venv for the wheel smoke test outside the checkout
- **Companion handoff:** `docs/handoffs/CLAUDE_RE_REVIEW_SLICE_001_1.md`
- **Historical evidence preserved:** `docs/REVIEW_LOG.md` was not modified by this re-review.

Every status below is based on my own probe scripts and command runs at `54748ff`, not on
Codex's reported results. Line references are to the re-reviewed commit.

## Status summary — original findings

| Finding | Original severity | Status |
|---|---|---|
| LIB-R-001 invalid FX rates | BLOCKER | **VERIFIED CLOSED** |
| LIB-R-002 cross-batch invoice duplicates | MAJOR | **PARTIALLY CLOSED** (original exploits dead; ownership rank regression LIB-RR-001) |
| LIB-R-003 committed-output reconciliation | MAJOR | **VERIFIED CLOSED** (quality-evidence attestation gap noted as LIB-RR-004) |
| LIB-R-004 non-finite financial values | MAJOR | **VERIFIED CLOSED** |
| LIB-R-005 duplicate/conflicting FX rows | MAJOR | **VERIFIED CLOSED** |
| LIB-R-006 referential integrity | MAJOR | **VERIFIED CLOSED** |
| LIB-R-007 replay/version identity | MAJOR | **VERIFIED CLOSED** (evidence-existence nit noted as LIB-RR-005) |
| LIB-R-008 storage contract completeness | MAJOR | **VERIFIED CLOSED** |
| LIB-R-009 ambiguous date/decimal formats | MINOR | **VERIFIED CLOSED** |
| LIB-R-010 Windows path length | MINOR | **PARTIALLY CLOSED** (shortening works; shipped guard test is brittle, LIB-RR-003) |
| LIB-R-011 volume counting | MINOR | **VERIFIED CLOSED** |
| LIB-R-012 per-batch evidence grain | MINOR | **ACCEPTED POLICY CONFIRMED** |
| LIB-R-013 missing-summary replay crash | MINOR | **VERIFIED CLOSED** |
| LIB-R-014 CSV formula injection | MINOR | **VERIFIED CLOSED** (system-of-record mutation side effect, LIB-RR-006) |
| LIB-R-015 wheel unusable outside checkout | MINOR | **VERIFIED CLOSED** |
| LIB-R-016 quality-failed publication policy | MINOR | **ACCEPTED POLICY CONFIRMED** |
| LIB-R-017 undocumented rounding policy | MINOR | **VERIFIED CLOSED** |
| LIB-R-018 negative-path test gaps | MINOR | **VERIFIED CLOSED** |
| LIB-R-019 single-writer documentation | SUGGESTION | **VERIFIED CLOSED** (Delta transaction scope nit, LIB-RR-009) |
| LIB-R-020 missing workflow artifacts | SUGGESTION | **VERIFIED CLOSED** |

**New findings:** LIB-RR-001 (MAJOR), LIB-RR-002 (MAJOR), LIB-RR-003 … LIB-RR-007 (MINOR),
LIB-RR-008 … LIB-RR-010 (SUGGESTION). Details after the per-finding evidence.

---

## Original findings — independent evidence

### LIB-R-001 — Invalid FX rates (BLOCKER) — VERIFIED CLOSED

- **Probe:** my original exploit re-run (`probe_a_fx.py`): every GBP rate set to `0.000000`,
  then `-1.000000`, against otherwise healthy batches; plus the repo's parametrized suite
  covering `NaN`, `Infinity`, `-Infinity`, `malformed` (read and independently executed in the
  full run).
- **Result:** both runs are `quality_failed` with `VALID_EXCHANGE_RATES` failed; all 365 GBP
  rate rows quarantined `INVALID_EXCHANGE_RATE`; all 144 dependent GB invoices quarantined
  `INVALID_EXCHANGE_RATE_REFERENCE` with empty `amount_eur`; **zero GB rows in Silver**;
  reported revenue 714,544.39 is the genuinely trusted remainder and is finite. Missing rates
  still produce `MISSING_EXCHANGE_RATE` (demo scenario re-verified end to end).
- **Where:** `src/datalibra/silver/pipeline.py:112-122` (finite, `> 0`),
  `:400-417` (invalid keys excluded from usable rates), `:451-473` (dependent facts withheld
  with explicit reasons); `config/quality-rules/slice_001.json` marks the new rules critical.
- **Remaining risk:** none for this exploit class. No plausibility band exists — an extreme but
  finite positive rate (e.g. 9.999999) converts; that is the documented, deliberate policy
  boundary awaiting a finance-owned band.

### LIB-R-002 — Cross-batch invoice duplicates (MAJOR) — PARTIALLY CLOSED

- **Probes:** three-batch scenarios in both orders (`probe_b_crossbatch.py`, `probe_b4.py`),
  plus the repo's own two tests.
- **Original exploits — all dead:**
  - Exact redelivery under a second batch ID: global Silver stays 720 rows; the redelivered
    720 rows are quarantined `CROSS_BATCH_DUPLICATE_INVOICE`; revenue not inflated. Also
    re-demonstrated through my independent in-memory adapter.
  - Conflicting claim at 10× the amount (full-size batch, both processing orders): the
    contested invoice is withheld from Silver entirely, both occurrences quarantined
    `CONFLICTING_DUPLICATE_INVOICE`, unrelated rows in the second batch intact
    (1438 = 1440 − 2 trusted), identical outcome forward and reverse.
  - Correcting the conflicting owner (repo test + probe): resolves only the intended claims;
    720 rows per batch afterwards; correcting batch A no longer erases batch B's contribution.
- **Not closed:** the ownership invariant "exact redelivery keeps the earliest active owner"
  does not hold over time — ownership silently flips to the alphabetically-smallest batch ID
  on the next unrelated run, and with rate-divergent claims the trusted EUR value changes.
  See **LIB-RR-001** for the reproduction (trusted total moved 916,351.47 → 933,811.44 on a
  green run).
- **Required action:** fix LIB-RR-001; then LIB-R-002 can be marked closed.

### LIB-R-003 — Committed-output reconciliation (MAJOR) — VERIFIED CLOSED

- **Probes:** the repo's three fault adapters (drop half, alter amount, omit batch) executed in
  the full suite, plus my own **composition-based** `DelegatingFaultStorage`
  (`probe_c_faults.py`) covering four more corruptions.
- **Result:** duplicate committed business key → detected (row + financial FAIL); stale
  committed reads → detected (11 FAIL rows); dropped quarantine evidence → detected
  (`COMMITTED_READBACK_MISMATCH` via quarantine signatures); drop half / alter amount /
  omit contribution → detected. In every detected case status is `quality_failed` and the
  refresh watermark does not advance. Reconciliation genuinely re-reads committed Silver and
  quarantine through `PipelineStorage` (`pipeline.py:592-688`) and compares keys, counts,
  per-batch contributions, and EUR totals against expected post-commit state.
- **Gap:** dropped **quality evidence** is not detected (quality rows are written after
  reconciliation and never read back) — recorded as LIB-RR-004 (MINOR). The original finding's
  scope (trusted rows, quarantine, totals) is fully closed.

### LIB-R-004 — Non-finite financial values (MAJOR) — VERIFIED CLOSED

- **Probes:** `NaN` invoice revenue (my original exploit re-run); repo parametrized tests for
  `NaN`, `sNaN`, `Infinity`, `-Infinity`, malformed, negative revenue and negative budget, and
  the zero-revenue boundary — all independently executed.
- **Result:** the NaN row is quarantined `INVALID_FINANCIAL_VALUE`, never enters Silver;
  summary revenue is finite (915,219.85 = total minus the affected invoice); no non-finite
  value exists in any Silver, summary, or reconciliation file (`decimal_string` refuses
  non-finite values at `normalization.py:69-72`; `parse_decimal` rejects them at `:56-66`).
  Negative budgets quarantined; zero revenue correctly trusted. Failure messages are
  deterministic strings.

### LIB-R-005 — Duplicate and conflicting FX rows (MAJOR) — VERIFIED CLOSED

- **Probe:** `probe_de.py` — duplicate placed *before* the original; three identical
  duplicates; two-equal-plus-one-conflicting with the conflict first in file order;
  conflicting March GBP rate affecting budgets (multi-dataset dependents); plus repo tests.
- **Result:** exact duplicates collapse to one deterministic trusted rate with
  `DUPLICATE_EXCHANGE_RATE` quarantine for the rest, independent of position; any conflict
  withholds **every** occurrence (`CONFLICTING_EXCHANGE_RATE`), publishes no trusted rate for
  the key, and quarantines dependent invoices/shipments/budgets with
  `CONFLICTING_EXCHANGE_RATE_REFERENCE`. No last-write-wins path remains
  (`pipeline.py:361-383`).

### LIB-R-006 — Referential integrity (MAJOR) — VERIFIED CLOSED

- **Probes:** unknown country/currency/customer/cost-center/shipment on invoices (repo
  parametrized test, executed); master-data checks (country→currency, customer/cost-center→
  country, rate→currency); my false-positive probe (`probe_de.py`): mixed-case + padded
  identifier, country alias "Germany", whitespace-only identifier, inner-space identifier.
- **Result:** every unknown reference quarantines with its precise `UNKNOWN_*` code and the
  row never reaches Silver; invalid dimension rows are excluded from the valid reference sets
  so facts referencing them cascade correctly. Normalization produces no false positives:
  ` cus-de-001 ` → trusted, `Germany` → `DE` trusted, `CUS DE 002` → trusted, whitespace-only
  → `MISSING_CUSTOMER_ID`.

### LIB-R-007 — Replay and version identity (MAJOR) — VERIFIED CLOSED

- **Probes:** repo tests (pipeline/data-contract/rules-version mismatch each force a rebuild;
  missing summary rebuilds; interrupted publication leaves no state and retry converges) plus
  my matrix (`probe_fgijk.py`): state deleted with committed output present → reprocessed to a
  correct converged result; unchanged compatible input → `already_processed`; two sequential
  corrections converge with all three Bronze versions retained.
- **Versions require no Git at runtime:** `PIPELINE_VERSION` is a package constant
  (`src/datalibra/__init__.py`), `DATA_CONTRACT_VERSION` a contracts constant, and the rules
  version a SHA-256 of the canonicalized quality config (`config/loader.py:36-38`) — verified
  working from the installed wheel outside the checkout.
- **Nits:** deleting `silver/invoices.csv` while state+summary are intact still returns a
  no-op without restoring it (LIB-RR-005, MINOR — the published acceptance criterion only
  promises summary compatibility, which is what is implemented); a malformed state file raises
  a raw `JSONDecodeError` (LIB-RR-008, SUGGESTION).

### LIB-R-008 — Storage contract completeness (MAJOR) — VERIFIED CLOSED

- **Evidence:** `grep` of orchestration shows 14 distinct `storage_adapter.*` calls, all
  declared on `PipelineStorage` (`storage/base.py:9-77`); `process_batch` accepts an injected
  adapter (`pipeline.py:267-288`) and constructs `LocalCsvStorage` only as the default; source
  schemas, dataset order, fingerprint, storage-ID, and canonical-payload definitions live in
  neutral `domain/contracts.py`; the generator and test helpers import from it (generator no
  longer owns any shared contract).
- **Probe:** I wrote my own minimal in-memory adapter from the protocol alone
  (`probe_h_adapter.py`, no `LocalCsvStorage` internals) and ran the full pipeline through it:
  healthy success with 720 trusted invoices and revenue 916,351.47, `already_processed`
  replay, and correct cross-batch dedup behavior, with nothing written to the filesystem.
  `isinstance(store, PipelineStorage)` holds.

### LIB-R-009 — Ambiguous input formats (MINOR) — VERIFIED CLOSED

- `normalize_date` accepts only `YYYY-MM-DD` (regex + `date.fromisoformat`); `01/02/2025`,
  `14.03.2025`, `2025-02-31` all raise. `parse_decimal` rejects any comma or internal space
  (`"1,234"`, `"1 234.56"`, `"1.234,56"` all raise "Ambiguous decimal") and non-finite values.
  Verified by executing the parametrized unit tests and by direct calls.

### LIB-R-010 — Windows path length (MINOR) — PARTIALLY CLOSED

- **Closed part:** Bronze now uses a flat `bronze/<dataset>/<batch_id>-<20-hex>.csv` layout
  (~45 characters shorter than baseline); the full SHA-256 stays in provenance
  (`_source_fingerprint`), manifest, summary, and state; a short-ID collision with a different
  full fingerprint raises instead of overwriting (unit-tested, logic verified at
  `storage/local.py:81-101`). My probe run at a 166-character output root completed
  successfully — the baseline code failed near ~140.
- **Not closed:** the shipped guard test itself is environment-brittle — see LIB-RR-003. It
  failed in my environment (`assert 242 < 240`), so the "82 passed" claim is not portable.
  There is still no actionable diagnostic if a root deep enough to breach 260 is used.

### LIB-R-011 — Volume counting (MINOR) — VERIFIED CLOSED

- **Probe:** 72 distinct DE invoices → volume rule passes; 71 → fails; **50 distinct + 30
  duplicate copies → fails** (duplicates can no longer mask an incomplete partition). The
  threshold is an exact `Decimal` comparison over distinct invoice IDs
  (`pipeline.py:418-430`).

### LIB-R-012 — Per-batch evidence grain (MINOR) — ACCEPTED POLICY CONFIRMED

- `docs/DATA_QUALITY_RULES.md` now states the per-batch audit grain explicitly and directs
  steward KPIs to distinct business keys. Behavior matches (exact redelivery quarantines the
  redelivered occurrences under their own batch). Reasonable, documented policy.

### LIB-R-013 — Missing-summary replay crash (MINOR) — VERIFIED CLOSED

- Deleting the run summary while state exists now triggers a logged rebuild that rewrites the
  summary (repo test + my probe F-series); no raw `FileNotFoundError`, no false no-op.

### LIB-R-014 — CSV formula injection (MINOR) — VERIFIED CLOSED

- Steward-facing Silver/quarantine/claims/quality writes prefix `= + - @ \t \r`-leading values
  with `'` (`storage/local.py:32-35`); Bronze retains the exact source bytes (verified:
  `=HYPERLINK(...)` raw in Bronze, neutralized in quarantine; `=2+2` neutralized in Silver).
  Side effect recorded as LIB-RR-006: the neutralization mutates the system of record, and a
  business-key value beginning with a protected character triggers a false reconciliation
  failure.

### LIB-R-015 — Wheel portability (MINOR) — VERIFIED CLOSED

- Wheel `datalibra-0.1.1` built from a clean venv contains
  `datalibra/config_defaults/{datasets,quality-rules}/slice_001.json`; installed into a
  separate venv in a neutral directory, `libra generate healthy` and `libra run healthy`
  succeed (revenue 916,351.47, exit 0) and `libra run broken` returns exit 2 with the three
  documented quality failures — all without a repository checkout. A unit test pins packaged
  defaults equal to the repo config. CI now installs and smoke-tests the wheel.

### LIB-R-016 — Quality-failed publication policy (MINOR) — ACCEPTED POLICY CONFIRMED

- Valid rows publish under `quality_failed` and the trusted refresh watermark does not advance
  (verified in fault probes: `latest_successful_refresh_timestamp` stays `None`);
  `docs/DATA_QUALITY_RULES.md` and `docs/ARCHITECTURE.md` state the policy and the consumer
  gate explicitly. Explicit, documented, consistent.

### LIB-R-017 — Rounding policy (MINOR) — VERIFIED CLOSED

- `docs/KPI_DEFINITIONS.md` and `docs/DATA_MODEL.md` document per-transaction two-decimal
  `ROUND_HALF_UP` at conversion with totals as sums of rounded values; the boundary case is
  unit-tested; my baseline independent recomputation (916,351.47 under exactly this policy)
  still matches.

### LIB-R-018 — Negative-path coverage (MINOR) — VERIFIED CLOSED

- 56 new tests across validation, reference integrity, FX conflicts, cross-batch ownership,
  committed-corruption, replay/version, packaging, path length, and CSV safety; independently
  executed (81 of 82 pass here; the one failure is the brittle path-guard test, LIB-RR-003,
  not a production defect). Branch coverage 96.91%.

### LIB-R-019 — Single-writer documentation (SUGGESTION) — VERIFIED CLOSED

- `docs/ARCHITECTURE.md` ("The local adapter is single-writer … state is written last; rerun
  is the crash-recovery mechanism") and `AGENTS.md` state the constraint; nothing implies safe
  multi-writer use. ADR-003 requires a serializable Delta transaction — scope nit in
  LIB-RR-009.

### LIB-R-020 — Workflow artifacts (SUGGESTION) — VERIFIED CLOSED

- `AGENTS.md`, `docs/handoffs/CODEX_SLICE_001.md` (accurate historical record),
  `CODEX_REMEDIATION_PLAN_001_1.md`, `CODEX_REMEDIATION_SLICE_001_1.md` all exist and are
  linked from `docs/README.md`; contents match the verified history.

---

## New findings

### LIB-RR-001 — Invoice ownership rank is derived from the alphabetized state file; ownership and trusted EUR amounts silently change on later unrelated runs

- **Severity:** MAJOR
- **Where:** `src/datalibra/silver/pipeline.py:487-489` (`active_batch_order =
  list(state.get("batches", {}))` + append), `:180-216` (`_resolve_invoice_claims` ranks by
  that order); `src/datalibra/storage/local.py:66-72` (`write_json_atomic` uses
  `sort_keys=True`, so state `batches` keys are **alphabetized on disk** and `read_state`
  returns them in alphabetical, not arrival, order)
- **Evidence (reproduced, `probe_b_crossbatch.py`):**
  1. Process `zulu-first` (healthy, 720 invoices), then `alpha-second` (exact redelivery).
     During alpha's own run the owner is correctly `zulu-first` (arrival order is still
     intact in memory).
  2. Process an unrelated `middle-third` (disjoint invoice IDs). Its run reloads state —
     now alphabetized to `['alpha-second', 'middle-third', 'zulu-first']` — re-resolves all
     claims, and **flips ownership of all 720 original invoices to `alpha-second`**; the
     cross-batch quarantine flips attribution to `zulu-first`; `middle-third` reports
     **success** with no failed rule.
  3. Financially material variant: `alpha-second` redelivers the same canonical invoices but
     its FX file carries GBP rates +0.10 (canonical payload excludes the applied rate, so
     this is classified as an *exact* replay). After the flip, GB invoice
     `INV-2025-000037` changed from 1,069.07 EUR (zulu) to 1,161.56 EUR (alpha), and the
     trusted total of the original 720 invoices moved from **916,351.47 to 933,811.44** —
     a silent +17,459.97 EUR change on a green, unrelated run.
- **Why it matters:** this re-creates, through the remediation's own mechanism, the class of
  defect LIB-R-002 was meant to end: trusted amounts changing with no owning correction and
  no failed rule. It also invalidates prior batch summaries (zulu's stored summary still
  claims 720 rows/916,351.47) and breaks the documented invariant "exact cross-batch replays
  keep the earliest active owner" (ADR-003, `docs/DATA_QUALITY_RULES.md`). Outcomes depend on
  batch-ID lexicography versus arrival order — `slice001-*` demo names happen to mask it, and
  the repo's cross-batch tests never trigger a third-run re-resolution.
- **Probe used:** `probe_b_crossbatch.py` scenarios S1–S3 (transcript in the handoff).
- **Remaining risk if unfixed:** any environment where batch IDs do not sort in arrival order
  (timestamped IDs mostly do; regional or source-prefixed IDs often do not) can silently
  restate trusted revenue whenever any batch is processed.
- **Required action:** persist an explicit, monotonic arrival sequence in state (e.g.
  `processed_sequence: N` per batch) and rank claims by it; never derive order from JSON key
  order. Additionally, treat canonically-identical claims whose converted `amount_eur`
  differs as **conflicts**, not exact replays, so an owner flip can never change EUR totals.
  Regression tests: three-batch flip scenario (alphabetically-earlier later batch) asserting
  stable ownership and stable totals; rate-divergent exact-replay scenario asserting
  withholding or stable amounts.

### LIB-RR-002 — The claims store is the undocumented system of record for Silver invoices; its loss silently erases previously trusted invoices under a green run

- **Severity:** MAJOR
- **Where:** `src/datalibra/silver/pipeline.py:486-502` (trusted invoices are rebuilt from
  `read_claims` each run), `:554-579` (`replace_all_silver` rewrites the entire Silver invoice
  table from the claims resolution), `:555` and `:609-613` (reconciliation's "expected" is
  derived from the same claims read, so claims loss is self-consistent and undetectable)
- **Evidence (reproduced, `probe_fgijk.py` section G):** process healthy batch (720 trusted
  invoices); delete `claims/invoices.csv`; process an unrelated second batch with disjoint
  invoice IDs. Result: second batch reports **success**, zero failed rules — and Silver now
  contains only the second batch's 720 rows; **all 720 previously trusted invoices are gone**
  from Silver. State and the first batch's summary still assert they exist. Every
  reconciliation row PASSes because expected and committed are both derived from the surviving
  claims.
- **Why it matters:** the committed-readback layer (LIB-R-003's fix) exists to catch exactly
  "trusted rows vanished from storage," yet the new architecture routes trust through a
  `claims/` file that (a) no documentation identifies as the invoice system of record —
  README describes it as "batch-owned invoice claims used for global deduplication" — and
  (b) sits outside all attestation. Ironically `silver/invoices.csv` is now derived data that
  self-heals from claims, while claims themselves have no integrity check against state.
  The claims table also grows with every active batch forever (no pruning or compaction
  policy), which is the unbounded-growth concern for the Delta port.
- **Probe used:** `probe_fgijk.py` (section G).
- **Remaining risk if unfixed:** any partial restore, cleanup script, or sync tool that
  touches `claims/` can silently delete recognized revenue while dashboards stay green.
- **Required action:** cross-check resolution inputs against processed state — every batch
  recorded in state as contributing trusted invoices must be represented in claims; a missing
  batch contribution fails reconciliation (`COMMITTED_READBACK_MISMATCH`) instead of
  shrinking Silver. Document `claims/` as trust-critical evidence, include it in the future
  Delta transaction scope, and define its lifecycle (pruning/archival policy). Regression
  test: delete claims (whole file and single-batch subset) and assert the next run fails
  reconciliation rather than reporting success.

### LIB-RR-003 — The deep-path guard test fails in ~1/7 of environments; the "82 passed" claim is not portable

- **Severity:** MINOR
- **Where:** `tests/integration/test_pipeline.py:55-68`
- **Evidence:** in my environment the suite is **81 passed, 1 failed** — the failure is
  `assert 242 < 240` inside `test_deep_output_root_stays_below_practical_windows_path_limit`.
  The test's while-loop extends the root in 22-character segments until ≥145, so the final
  root length is 145–166 depending on `tmp_path` length modulo 22; roots ≥164 exceed the
  240-character assertion margin even though the pipeline itself **succeeded** (max real path
  238 + `.tmp`). The product behavior is fine; the guard is brittle and fails for roughly
  3 of every 22 possible basetemp lengths.
- **Required action:** pin the constructed root to an exact length (or assert against the
  relative-path budget instead of the absolute path), so the test result does not depend on
  the temp directory the runner happens to use. Optionally add the actionable too-long-path
  diagnostic originally recommended in LIB-R-010.

### LIB-RR-004 — Dropped quality evidence is not attested

- **Severity:** MINOR
- **Where:** `src/datalibra/silver/pipeline.py:690` (quality written after reconciliation; no
  read-back)
- **Evidence (`probe_c_faults.py`):** an adapter that acknowledges `replace_batch_quality` but
  persists nothing leaves `quality_results.csv` without the batch's rows; nothing detects it.
  The in-memory result (summary `failed_rules`, state status) remains correct, so trust
  decisions are unaffected — but the persisted audit trail can silently be incomplete.
- **Required action:** read back quality rows for the batch after writing and fail the run on
  mismatch, or explicitly document quality files as best-effort evidence excluded from
  attestation.

### LIB-RR-005 — A no-op replay does not verify committed trusted output still exists

- **Severity:** MINOR
- **Where:** `src/datalibra/silver/pipeline.py:290-314` (no-op requires matching state
  versions + readable summary only)
- **Evidence (`probe_fgijk.py` section F2):** delete `silver/invoices.csv` while state and
  summary are intact → rerun returns `already_processed` and the file stays missing. (State
  deletion, by contrast, correctly forces a rebuild — F1.) The published acceptance criterion
  only promises fingerprint/version/summary compatibility, so this matches documentation —
  but the remediation plan's stronger wording ("required evidence exists") is not implemented.
- **Required action:** either extend the no-op gate with a cheap existence/count check of the
  batch's committed contribution, or align the plan/ADR wording with the implemented check.

### LIB-RR-006 — Spreadsheet neutralization mutates the system of record and can raise false reconciliation failures

- **Severity:** MINOR
- **Where:** `src/datalibra/storage/local.py:32-35`, applied on every Silver/claims/quarantine/
  quality write (`protect_spreadsheets=True`)
- **Evidence (`probe_fgijk.py` section H):** a valid customer with `customer_id = "=CUS-DE-999"`
  is stored in Silver as `'=CUS-DE-999`; committed-readback then mismatches the in-memory
  expected key and the run fails `SOURCE_TARGET_ROW_RECONCILIATION` — a false positive (loud,
  not silent, so the failure direction is safe). The stored identifier no longer equals the
  source value, and claims round-trips can propagate the mutated form.
- **Required action:** neutralize on export/read for stewards (or strip the guard prefix on
  read-back comparison), keeping stored trusted values byte-faithful to standardized source
  values. At minimum document that business keys must not begin with `= + - @`.

### LIB-RR-007 — Non-invoice facts still have last-write-wins cross-batch ownership

- **Severity:** MINOR
- **Where:** `src/datalibra/silver/pipeline.py:556-586` (shipments/budgets/dimensions use
  `replace_batch_and_merge_silver` upsert; claims protection covers invoices only)
- **Evidence (`probe_fgijk.py` section K):** a second batch redelivering `SHP-2025-000001`
  with `revenue_amount 99999.00` silently replaced the trusted shipment row (owner flipped to
  the new batch) with no dedup/conflict signal; the upsert is reconciliation-"expected," so
  nothing fails on the overwrite itself. Shipment revenue is documented as operational
  comparison, not recognized revenue, so the financial KPI surface is unaffected — but the
  same silent-rewrite class LIB-R-002 removed for invoices remains for every other dataset.
- **Required action:** either extend claim-based ownership to shipments and budgets in a
  future slice, or document explicitly that cross-batch key ownership for non-invoice
  datasets is last-write-wins by design.

### LIB-RR-008 — Malformed state file crashes with a raw JSONDecodeError

- **Severity:** SUGGESTION
- **Evidence (`probe_fgijk.py` F3):** corrupt `state/processed_batches.json` → unhandled
  `json.JSONDecodeError`. Consistent with the execution-failure taxonomy, but a wrapped error
  naming the file and the recovery path (delete state to force replay) would be better.

### LIB-RR-009 — The Delta transaction contract omits reconciliation evidence and summaries from its atomic scope

- **Severity:** SUGGESTION
- **Evidence:** ADR-003 and the remediation handoff require a serializable Delta transaction
  over "trusted data, quarantine, quality evidence, and state" — reconciliation artifacts and
  run summaries are not listed. The local design treats them as pre-state evidence; the Delta
  contract should name them explicitly so the adapter cannot claim compliance while committing
  them non-atomically.

### LIB-RR-010 — Residual "DataLibraFinance" name in the Power BI contract

- **Severity:** SUGGESTION
- **Evidence:** `powerbi/README.md:7` instructs naming the future PBIP project
  `DataLibraFinance`; the project is Libra (README title, docs) and the package is
  `datalibra`. Rename the planned PBIP to a Libra-consistent name for coherence.

---

## Design-question follow-ups confirmed as policy

- Country partitions are still withheld individually (probe: partial-batch volume behavior
  unchanged); invoice-date FX selection and `ROUND_HALF_UP` are now documented; conflicting
  duplicates now withhold **all** occurrences (the stricter option recommended in the original
  review) — verified in both processing orders.
- The local adapter's actual guarantees (per-file atomicity, state-last ordering, rerun
  recovery, single writer) match its documented scope; nothing implies multi-writer safety.
