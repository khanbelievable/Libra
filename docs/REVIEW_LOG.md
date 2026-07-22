# Slice 001 Independent Review Log

- **Reviewer:** Claude (independent senior data-engineering review)
- **Date:** 2026-07-22
- **Commit reviewed:** `40ac981` (`main`, clean working tree)
- **Environment:** Windows 11, Python 3.12.10, fresh `.venv`, editable install per README
- **Companion document:** `docs/handoffs/CLAUDE_REVIEW_SLICE_001.md` (commands, exact outputs, verdict)

Every finding below was either reproduced by executing code against generated batches
(probe scripts run during this review) or verified by direct source inspection. Findings
are ordered by severity. Line numbers refer to the reviewed commit.

---

## LIB-R-001 — No sanity rule on exchange-rate values; zero or negative rates silently corrupt trusted revenue

- **Severity:** BLOCKER
- **Where:** `src/datalibra/silver/pipeline.py:281-291` (rate applied unconditionally),
  `src/datalibra/silver/pipeline.py:243-246` (rates loaded without validation),
  `src/datalibra/domain/normalization.py:62-69` (`parse_decimal` accepts any Decimal)
- **Evidence (reproduced):** Set every GBP `rate_to_eur` to `0.000000` in an otherwise
  healthy batch: run completed with `status: success`, **zero failed rules**, 720/720
  invoices trusted, and trusted revenue silently fell from 916,351.47 to **714,544.39**;
  144 GB invoices sit in Silver with `amount_eur = 0.00`. Repeat with `-1.000000`:
  `status: success`, GB invoices trusted with **negative** EUR amounts, trusted revenue
  539,944.09. All quality rows PASS in both runs.
- **Why it matters:** The project's core claim is that revenue cannot be silently lost or
  inflated. A one-character corruption in the FX feed (a plausible upstream defect)
  destroys a quarter of trusted revenue while every dashboard shows green. This defeats
  `EXCHANGE_RATE_EXISTS`'s purpose: the rate *exists*, it is just garbage.
- **Acceptance criterion affected:** "GBP facts without a same-date GBP/EUR rate are
  quarantined … and no EUR amount" (the guard covers absence but not invalidity);
  README claim "reject unsafe records … without inflating revenue".
- **Recommended change:** Add an `INVALID_EXCHANGE_RATE` reason (rule `EXCHANGE_RATE_EXISTS`
  or a new critical rule): a rate must be finite and `> 0` (optionally within a plausibility
  band per currency). Quarantine the rate row and every fact that would use it, exactly as
  for a missing rate.
- **Required regression test:** Unit + integration: rate `0.000000`, negative rate, and
  absurd magnitude each produce quarantined facts with the new reason code, a FAIL rule row,
  and unchanged trusted revenue.

---

## LIB-R-002 — Cross-batch business-key collisions silently rewrite trusted revenue; batch replacement then erases the other batch's contribution

- **Severity:** MAJOR
- **Where:** `src/datalibra/silver/pipeline.py:260-276` (`seen_invoice_ids` is per-run only),
  `src/datalibra/storage/local.py:73-90` (`replace_batch_and_merge_silver`: line 82 retains
  rows of other batches, lines 86-87 upsert by business key regardless of owner batch)
- **Evidence (reproduced):** Process healthy batch A (revenue 916,351.47). Process batch B
  (`batch_id: slice001-late-feed`) re-delivering the full Germany partition with
  `INV-2025-000001` at 10× its amount. Result: the Silver row became 11,316.20 owned by
  batch B, total trusted EUR rose to **926,536.05**, and `DUPLICATE_INVOICE` reported
  **PASS** for batch B. Then a corrected batch A was reprocessed: `INV-2025-000001`
  reverted to A's value and **batch B's entire Silver contribution dropped to 0 rows** —
  key ownership ping-pongs with replay order. (In this probe batch B tripped the volume
  rule for the four absent countries, but a full five-country resend passes fully green;
  the volume rule is not a defense.)
- **Why it matters:** `DUPLICATE_INVOICE` protects only within one physical file. A late or
  supplemental feed under a new batch ID — a routine event — can inflate or rewrite
  recognized revenue with no quarantine, no audit signal, and no failed rule, and the
  "replace prior contribution" guarantee (ADR-003) silently destroys another batch's data
  when keys collide across batches.
- **Acceptance criterion affected:** "Duplicate invoice occurrences are quarantined and
  cannot inflate Silver revenue"; ADR-003 "corrections … must not duplicate finance
  results".
- **Recommended change:** On merge, detect incoming business keys already owned by a
  *different* batch ID. Either quarantine the incoming rows with a new reason
  (`CROSS_BATCH_DUPLICATE`), or require an explicit supersession flag and write an
  overwrite-audit record (old batch, old value, new batch, new value). Never let an
  ordinary merge change a key's owning batch silently.
- **Required regression test:** Two-batch integration test asserting (a) a colliding key
  from a second batch is quarantined/audited, not silently upserted; (b) reprocessing the
  first batch cannot remove or revert the second batch's surviving rows.

---

## LIB-R-003 — Row and financial reconciliation is tautological: it compares in-memory partitions of the same list and never inspects persisted output

- **Severity:** MAJOR
- **Where:** `src/datalibra/silver/pipeline.py:354-415` (`source_count = len(standardized[...])`,
  trusted/quarantined are the same objects partitioned at lines 293-305; `_sum_eur` runs over
  the same in-memory rows), writes happen afterwards at lines 417-427 with no read-back
- **Evidence (reproduced):** Monkeypatched the storage adapter to silently drop **half of
  every Silver dataset** during the write. Run result: `status: success`, summary claims 720
  Silver invoices, disk contains 360, and **all** `SOURCE_TARGET_*` rows are PASS. By
  construction `source == trusted + quarantined` cannot fail (the only observed failure mode
  is NaN poisoning, see LIB-R-004 — a comparison artifact, not a control).
- **Why it matters:** The README sells "source-to-target row and financial reconciliation"
  as trust evidence, and `tests/demo` asserts these PASS rows. A control that cannot fail
  is not a control; it will port to the Delta adapter as false assurance precisely where
  transactional bugs would live. The demo assertion on these rows is a false-positive test.
- **Acceptance criterion affected:** "Bronze, Silver, quarantine, quality result,
  reconciliation … evidence is persisted" (the evidence does not attest what was persisted);
  `docs/DATA_QUALITY_RULES.md` `ROW_COUNT_MISMATCH` / `FINANCIAL_TOTAL_MISMATCH` semantics.
- **Recommended change:** After publication, re-read persisted Bronze, Silver (filtered to
  this batch), and quarantine files and reconcile those counts/totals against the manifest.
  Keep the in-memory check if desired, but the persisted comparison is the one that counts.
- **Required regression test:** Fault-injection test with a lossy storage adapter asserting
  `SOURCE_TARGET_ROW_RECONCILIATION` FAILs and status is not `success`.

---

## LIB-R-004 — `NaN`/`Infinity` amounts pass validation, enter Silver, and turn the run summary into `"NaN"`

- **Severity:** MAJOR
- **Where:** `src/datalibra/domain/normalization.py:62-69` (`Decimal("NaN")` and
  `Decimal("Infinity")` parse successfully), `:72-73` (quiet NaN propagates through
  `quantize`), `src/datalibra/silver/pipeline.py:286-291`
- **Evidence (reproduced):** One invoice with `revenue_amount = "NaN"`: the row is **not
  quarantined**, lands in Silver with `amount_eur = NaN`, the persisted run summary reads
  `"trusted_invoice_revenue_eur": "NaN"`, and the only FAIL is
  `SOURCE_TARGET_FINANCIAL_RECONCILIATION` — an accident of `NaN != NaN`, misattributed to
  reconciliation instead of the offending row.
- **Why it matters:** A malformed amount is a row-level data-quality failure; here it
  poisons the trusted table and every downstream aggregate, and the evidence trail points a
  steward at reconciliation rather than the bad row. `Infinity` behaves analogously.
- **Acceptance criterion affected:** "Silver dates/codes/identifiers/decimals conform to
  documented contracts"; separation of quality failures from execution failures.
- **Recommended change:** Reject non-finite values in `parse_decimal` (or validate in
  `_standardize_fact`) and quarantine the row with an `INVALID_AMOUNT` reason under
  `REQUIRED_IDENTIFIERS`-style critical handling. `decimal_string` should assert finiteness.
- **Required regression test:** Rows with `NaN`, `-Infinity`, `sNaN` amounts are quarantined
  with the new reason; Silver contains no non-finite value; summary revenue stays numeric.

---

## LIB-R-005 — Conflicting duplicate exchange-rate rows are resolved silently, last occurrence wins

- **Severity:** MAJOR
- **Where:** `src/datalibra/silver/pipeline.py:243-246` (dict comprehension: later rows
  overwrite earlier `(rate_date, currency_code)` keys), `src/datalibra/storage/local.py:83-88`
  (Silver merge dedupes on the same key, keeping the last)
- **Evidence (reproduced):** Appended a second `2025-01-01/GBP` row with `rate_to_eur =
  2.000000` (original 1.155588). Run: `status: success`, no failed rules, Silver holds one
  row with **2.000000**. Any fact dated that day would convert at the bogus rate with no
  signal.
- **Why it matters:** Exchange rates scale every EUR amount in the system. `exchange_rates`
  has a declared business key (`config/datasets/slice_001.json`), yet uniqueness is never
  enforced — the duplicate-protection story applies only to invoices. Silent last-wins on
  reference data is the same failure class the project exists to prevent.
- **Acceptance criterion affected:** README "Quarantine of duplicate invoices …" implies a
  duplicate-safety posture; `docs/DATA_QUALITY_RULES.md` has no rate-duplicate rule (gap).
- **Recommended change:** Enforce business-key uniqueness on every dataset during
  standardization. Identical duplicate rows may collapse silently; **conflicting**
  duplicates on reference data should fail a critical rule and withhold the affected key
  (and dependent facts) pending steward decision.
- **Required regression test:** Batch with conflicting duplicate rate rows produces a FAIL
  rule row and no fact converted at either contested value.

---

## LIB-R-006 — No referential-integrity check on `country_code`; unknown countries flow into Silver and evade the volume rule

- **Severity:** MAJOR
- **Where:** `src/datalibra/silver/pipeline.py:261-280` (checks cover customer, cost
  center, shipment only), `:248-255` (`dropped_countries` iterates *expected* countries, so
  unknown codes are invisible to the volume rule)
- **Evidence (reproduced):** Invoice with `country_code = "XX"`: `status: success`, no
  failed rules, the row is trusted in Silver with country `XX`.
- **Why it matters:** Country is a first-class reporting dimension (country marts, the
  volume rule, Power BI relationships). Unattributable revenue makes total-vs-by-country
  reconciliation fail downstream. README line 19 claims quarantine of "unknown references"
  generally; the implementation covers three of the four fact references.
- **Acceptance criterion affected:** "Missing and unknown customer/cost-center/shipment
  identifiers are detectable and quarantined" (criterion itself omits country — the docs and
  code share the gap; README wording overclaims).
- **Recommended change:** Add `UNKNOWN_COUNTRY_CODE` under `REFERENTIAL_INTEGRITY` for all
  fact datasets carrying `country_code`; optionally also validate `currency_code` against
  the currencies dimension so the failure reads "unknown currency", not "missing rate".
- **Required regression test:** Fact rows with unknown country (and unknown currency) are
  quarantined with precise reason codes.

---

## LIB-R-007 — Replay state has no pipeline version; `already_processed` vouches for outputs written by an incompatible older pipeline

- **Severity:** MAJOR
- **Where:** `src/datalibra/silver/pipeline.py:196-204` (no-op decision considers only
  batch ID + fingerprint), `:453-459` (state records fingerprint/scenario/status only)
- **Evidence (observed live during this review):** This machine's `data/verification/processed/healthy`
  was produced by an **older code version** (Bronze written as
  `bronze/<dataset>/<batch_id>.csv`; current contract is
  `bronze/<dataset>/<batch_id>/<fingerprint>.csv`). Running today's CLI over that directory
  returned `already_processed` and re-asserted the old summary — the current pipeline
  attested evidence that does not match its own documented Bronze contract.
- **Why it matters:** "Same input seen before" is not "outputs conform to current
  contracts". Locally this yields stale demo evidence; in the Delta adapter the same logic
  would skip required reprocessing after schema/logic migrations.
- **Acceptance criterion affected:** "Re-running an unchanged batch is a no-op with
  identical Silver counts and totals" (the no-op must also imply contract-conformant
  outputs).
- **Recommended change:** Stamp a `pipeline_version` (and output-contract version) into
  state and summaries; a version mismatch forces reprocessing (or an explicit migration
  path).
- **Required regression test:** State written with an older version marker triggers
  reprocessing instead of `already_processed`.

---

## LIB-R-008 — The storage abstraction is not yet a real seam: protocol covers 3 of 9 methods, the adapter is hard-coded, and the schema contract lives in the generator

- **Severity:** MAJOR
- **Where:** `src/datalibra/storage/base.py:9-28` (`PipelineStorage` declares only
  `write_bronze`, `replace_batch_and_merge_silver`, `replace_batch_quarantine`),
  `src/datalibra/silver/pipeline.py:196` (`storage = LocalCsvStorage(output_root)` — 
  concrete type constructed inside the domain pipeline; also uses `replace_batch_quality`,
  `read_state`, `write_state`, `write_reconciliation`, `write_summary`, `read_summary`,
  none of which are in the protocol), `src/datalibra/silver/pipeline.py:26`
  (`from datalibra.generators.synthetic import FIELDS` — the production schema contract is
  owned by the synthetic-data module), fingerprint algorithm triplicated in
  `pipeline.py:59-67`, `generators/synthetic.py:220-225`, `tests/helpers.py:23-37`
- **Evidence:** Source inspection as cited; a PySpark/Delta implementation of
  `PipelineStorage` cannot be injected without editing `process_batch`, and could not run
  the pipeline even if injected because six required methods are undeclared.
- **Why it matters:** ADR-004 and the README present "local CSV is an adapter, not the
  domain model" as a key decision. Today it is directionally true for normalization
  functions but not for the pipeline: the orchestration is a local-only script with an
  aspirational interface next to it. A reviewer probing the seam will find it decorative —
  worse for the portfolio than not claiming it. Importing the source-schema contract from
  `generators.synthetic` also means the validator and the data-faker cannot disagree, which
  weakens contract tests.
- **Acceptance criterion affected:** ADR-004 consequences ("contract fixtures must produce
  equivalent results across adapters"); Databricks README claim that the local protocol
  "defines the behavior the Delta adapter must preserve".
- **Recommended change:** Complete `PipelineStorage` to the real method set; accept the
  storage instance as a `process_batch` parameter (default local); move `FIELDS` (and the
  fingerprint function) into a neutral contract module (e.g. `datalibra.domain.schema`)
  imported by generator, pipeline, and tests.
- **Required regression test:** A contract-test that runs `process_batch` against a fake
  in-memory `PipelineStorage` implementation, proving the seam actually admits a second
  adapter.

---

## LIB-R-009 — Ambiguous source formats are silently reinterpreted: `"1,234"` becomes 1.234 and `01/02/2025` is assumed day-first

- **Severity:** MINOR
- **Where:** `src/datalibra/domain/normalization.py:62-69` (single-comma heuristic),
  `:43-59` (`/` and `.` formats hard-assume day-month-year)
- **Evidence (reproduced):** `parse_decimal("1,234") == Decimal("1.234")`. A US-style
  thousands value shrinks 1000×, silently. `normalize_date("01/02/2025")` returns
  `2025-02-01` regardless of the source's convention.
- **Why it matters:** The docstrings call these "explicit source formats", but nothing pins
  a format per source; a mis-declared regional feed corrupts amounts and dates without any
  quality signal. (European `1.234,56` is safely rejected; the US-thousands case is the
  silent one.)
- **Acceptance criterion affected:** "Silver dates/codes/identifiers/decimals conform to
  documented contracts."
- **Recommended change:** Make number/date format an explicit per-source (per-manifest)
  declaration and reject values that do not match it; at minimum reject integer-comma
  patterns like `\d{1,3}(,\d{3})+` as ambiguous.
- **Required regression test:** `"1,234"` and a group-separated variant raise/quarantine
  rather than parse; a date declared `mdy` is not parsed as `dmy`.

---

## LIB-R-010 — Windows MAX_PATH: fingerprint-named Bronze files crash with a confusing `FileNotFoundError` under moderately deep output roots

- **Severity:** MINOR
- **Where:** `src/datalibra/storage/local.py:61-71` (path
  `bronze/<dataset>/<batch_id>/<64-char sha256>.csv` + `.tmp` suffix), `:35-43`
- **Evidence (reproduced):** With an output root ~140 characters deep, the demo suite
  failed: `FileNotFoundError` opening a 265-character `.tmp` path (Windows non-long-path
  limit is 260). The entire test suite errors when pytest's basetemp is deep; it passes from
  a short basetemp. The error message gives no hint about path length.
- **Why it matters:** The project advertises Windows as a first-class platform (CI matrix,
  PowerShell demo script). Real user profiles (OneDrive-redirected folders, corporate temp
  paths) commonly exceed the remaining ~120-character budget; the failure masquerades as an
  execution failure with a misleading message.
- **Acceptance criterion affected:** "Installation succeeds … with the documented commands"
  on Windows in realistic directories.
- **Recommended change:** Use extended-length paths (`\\?\` prefix via `os.path` handling)
  or shorten the layout (e.g. 16-char fingerprint prefix directory, full fingerprint in the
  manifest/summary), and emit an actionable error when a write path exceeds the platform
  limit. Document the constraint.
- **Required regression test:** Windows CI (or unit test with a constructed long root)
  asserting either success via long-path handling or a clear diagnostic.

---

## LIB-R-011 — Country-volume rule counts duplicate occurrences and truncates the minimum

- **Severity:** MINOR
- **Where:** `src/datalibra/silver/pipeline.py:247` (`Counter` over standardized rows
  including duplicate invoice IDs), `:249-252` (`int(...)` truncates the product)
- **Evidence:** Source inspection; e.g. a country delivering 50 unique invoices plus 30
  resent copies counts 80 ≥ 72 and passes, though only 50 unique invoices arrived.
  Boundary behavior verified by probe: 72/144 delivered passes, 71/144 fails (matches the
  documented "below 50%" wording, but only because 144×0.50 is integral — with
  `expected = 145` the truncated minimum 72 admits 49.7% deliveries).
- **Why it matters:** The rule exists to catch incomplete partitions; resends (the exact
  failure the duplicate rule anticipates) can mask the incompleteness they accompany.
- **Acceptance criterion affected:** "A Germany invoice delivery approximately 70% below
  baseline fails `INVOICE_COUNTRY_VOLUME`."
- **Recommended change:** Count distinct invoice IDs per country; compute the threshold in
  `Decimal` and compare without truncation.
- **Required regression test:** Duplicates cannot lift a country over the threshold;
  non-integral thresholds round in the strict direction.

---

## LIB-R-012 — Identical content resent under a new batch ID doubles quarantine and quality evidence

- **Severity:** MINOR
- **Where:** `src/datalibra/storage/local.py:92-101` (quarantine replacement is scoped to
  one batch ID; other batches' physically identical rows are retained),
  `:103-119` (quality history likewise per batch)
- **Evidence (reproduced):** `duplicate_invoices` batch processed as A, then the same bytes
  re-manifested as batch B: Silver correctly stays at 720 rows, but
  `quarantine/invoices.csv` grows 12 → **24** rows for the same 12 physical resends.
- **Why it matters:** Steward-facing counts and the planned `Failed Quality Rows` measure
  double-count a single upstream event; quarantine evidence no longer reflects distinct
  problems. (Related to LIB-R-002 but a distinct effect: evidence inflation instead of
  Silver mutation.)
- **Acceptance criterion affected:** Quality-evidence auditability
  (`docs/DATA_QUALITY_RULES.md`).
- **Recommended change:** Either define quarantine grain explicitly as *per batch* in the
  docs and dashboards (count distinct business keys for steward KPIs), or deduplicate
  physically identical quarantine rows across batches by fingerprint.
- **Required regression test:** Documented expected quarantine count for an
  identical-content resend under a new batch ID.

---

## LIB-R-013 — Replay crashes with a raw `FileNotFoundError` when state exists but the run summary was lost

- **Severity:** MINOR
- **Where:** `src/datalibra/silver/pipeline.py:162-174` + `src/datalibra/storage/local.py:138-142`
- **Evidence (reproduced):** Delete `runs/slice001-healthy.json`, keep
  `state/processed_batches.json`, rerun: unhandled `FileNotFoundError`.
- **Why it matters:** State and evidence can genuinely diverge (partial cleanup, retention
  jobs). A replay path should self-heal (reprocess) or fail with a diagnostic naming the
  inconsistency, not a raw traceback.
- **Acceptance criterion affected:** Idempotent replay robustness (ADR-003).
- **Recommended change:** On summary read failure during the no-op path, log the
  inconsistency and reprocess the batch.
- **Required regression test:** Missing-summary-with-state case returns a reprocessed
  successful run.

---

## LIB-R-014 — Spreadsheet formula injection passes verbatim into steward-facing CSVs

- **Severity:** MINOR
- **Where:** `src/datalibra/storage/local.py:30-43` (values written unescaped),
  demo workflow instructs stewards to open quarantine/Silver CSVs
- **Evidence (reproduced):** `customer_name = =HYPERLINK("http://evil.example","click")`
  flows into `silver/customers.csv` unchanged; Excel would evaluate it on open.
- **Why it matters:** Quarantine files are precisely the ones humans open in Excel, and
  they contain the least-trusted data in the system. Synthetic data never triggers this,
  but the pipeline is presented as the pattern for real regional feeds.
- **Acceptance criterion affected:** `docs/SECURITY_AND_GOVERNANCE.md` steward-access
  posture.
- **Recommended change:** Offer (and default for quarantine) OWASP-style escaping of
  leading `= + - @ \t` in text fields, or document that local CSVs must not be opened with
  formula evaluation enabled.
- **Required regression test:** Quarantined value beginning with `=` is neutralized in the
  written CSV (if escaping is adopted).

---

## LIB-R-015 — The built wheel cannot run outside a repository checkout

- **Severity:** MINOR
- **Where:** `src/datalibra/config/loader.py:33-46` (walks up for `pyproject.toml`, then
  reads `<root>/config/...`), `pyproject.toml` (no data files packaged; CI builds a wheel)
- **Evidence:** Source inspection: an installed `libra` executed outside a checkout raises
  `FileNotFoundError: Could not find pyproject.toml`; inside an unrelated Python project it
  finds that project's `pyproject.toml` and then fails reading `config/`.
- **Why it matters:** CI's "Build wheel" step and `dist/` imply an installable artifact; the
  artifact only works from the repo. Not a Slice-001 blocker, but the gap between the
  packaging story and reality is the kind of detail technical reviewers probe.
- **Acceptance criterion affected:** "Installation succeeds on Python 3.12 with the
  documented commands" (holds for the documented editable install; wheel path is untested).
- **Recommended change:** Package the config as importlib resources with the repo files as
  overrides, or stop building/shipping a wheel until an adapter slice needs one.
- **Required regression test:** Smoke test installing the wheel into a clean venv and
  running `libra generate` from a neutral directory.

---

## LIB-R-016 — A `quality_failed` batch still publishes its valid rows to Silver; the trust boundary for direct Silver readers is undocumented

- **Severity:** MINOR
- **Where:** `src/datalibra/silver/pipeline.py:417-427` (publication happens before
  `failed_rules`/status are computed at `:429-439`); `docs/DATA_QUALITY_RULES.md` ("No row
  with any error reason enters Silver" — row-level only)
- **Evidence (reproduced):** In the cross-batch probe, a batch failing
  `INVOICE_COUNTRY_VOLUME` (critical) still merged 144 rows into Silver. The demo scenarios
  themselves rely on this semantics (720 Silver rows under a failed duplicate run), so it is
  intended — but only the refresh timestamp records the distinction, and nothing tells a
  Silver reader that current table content includes contributions from critically failed
  batches.
- **Why it matters:** "Latest successful refresh" protects dashboard freshness labels, but
  anyone consuming `silver/*.csv` (or the future Delta tables) directly gets failed-batch
  contributions indistinguishably. Combined with LIB-R-002 this widens the silent-mutation
  surface.
- **Acceptance criterion affected:** `docs/DATA_QUALITY_RULES.md` refresh semantics.
- **Recommended change:** Document the publication rule explicitly ("valid rows publish even
  when the batch fails critical rules; consume via the refresh gate"), or withhold
  publication for batches failing critical rules and stage them for steward release.
- **Required regression test:** Assertion pinning whichever publication semantics is chosen.

---

## LIB-R-017 — Monetary rounding mode is a finance-policy decision that lives only in code

- **Severity:** MINOR
- **Where:** `src/datalibra/domain/normalization.py:72-73` (`ROUND_HALF_UP`); no mention in
  `docs/KPI_DEFINITIONS.md`, `docs/DATA_MODEL.md`, or any ADR
- **Evidence (reproduced):** Recomputing healthy revenue from source with `ROUND_HALF_EVEN`
  yields 916,351.**46** vs the pipeline's 916,351.**47** — the published total depends on an
  undocumented choice.
- **Why it matters:** Finance sign-off requires the rounding rule to be an approved,
  documented policy (HALF_UP vs banker's rounding is an audit-relevant difference), and the
  Delta/Snowflake/DAX implementations must replicate it exactly.
- **Acceptance criterion affected:** KPI reproducibility across platforms (ADR-001).
- **Recommended change:** One sentence in `docs/KPI_DEFINITIONS.md` (and the FX section of
  the data model): per-transaction quantization to 2dp with ROUND_HALF_UP at conversion
  time, totals as sums of rounded values.
- **Required regression test:** Unit test pinning `decimal_string` rounding at the 0.005
  boundary (exists indirectly via `1.005 → 1.01`; extend to the conversion product path).

---

## LIB-R-018 — Test-suite gaps: the finance-critical negative paths are untested

- **Severity:** MINOR
- **Where:** `tests/` (suite of 25)
- **Evidence:** Source inspection of all tests. Untested today: the FX multiplication and
  rate-date lookup itself (no unit test converts a known amount at a known rate — the demo
  totals pin regressions but were captured from the pipeline's own output);
  `UNKNOWN_CUSTOMER_ID` / `UNKNOWN_COST_CENTER_ID` / `UNKNOWN_SHIPMENT_ID` (the entire
  `REFERENTIAL_INTEGRITY` FAIL path never fires in any test); multiple reason codes on one
  row; budgets quarantine; corrected batch whose previous quarantine contribution must be
  replaced; volume boundary (72 vs 71); `run-batch` CLI; execution-failure paths (schema
  mismatch, manifest count mismatch, invalid `batch_id`, stale fingerprint is the only one
  covered); duplicate-with-different-amount semantics. Branch coverage 94% is real but
  concentrated on happy paths — the uncovered 6% and the untested *data* paths are where
  the money moves.
- **Why it matters:** The suite proves the four demo scenarios and idempotent replay well,
  and the hardcoded expected literals are genuinely mutation-sensitive (rounding or FX
  direction changes would fail). But most protections this review found broken (LIB-R-001,
  -002, -004, -005, -006) were unprotected precisely because no test exercises them.
- **Acceptance criterion affected:** "Required tests: unit normalization/FX/rules" (BACKLOG
  LIBRA-001 — the FX unit tests it names do not exist).
- **Recommended change / required tests:** Add the regression tests listed per finding
  above, plus: one hand-computable FX unit test (e.g. 100.00 GBP × 1.155000 → 115.50), one
  referential-integrity integration test per unknown-reference reason, and one
  multi-reason-row test.

---

## LIB-R-019 — Single-writer assumption is undocumented (no locking on state or Silver)

- **Severity:** SUGGESTION
- **Where:** `src/datalibra/silver/pipeline.py:197` (state read) vs `:462` (state write);
  `src/datalibra/storage/local.py` (read-modify-write on shared CSVs; fixed `.tmp` names)
- **Evidence:** Source inspection; two concurrent `libra run` invocations can interleave
  read-modify-write on `silver/*.csv` and `processed_batches.json`, last write wins.
- **Why it matters:** Acceptable for a local demo, but it is exactly the guarantee Delta
  will change; stating the single-writer assumption makes the adapter contract sharper.
- **Recommended change:** One line in `docs/ARCHITECTURE.md` operational semantics; the
  Delta contract in LIB-R-002/LIBRA-004 should name serializable batch commits explicitly.
- **Required regression test:** None locally; Delta slice needs a concurrent-writer test.

---

## LIB-R-020 — Referenced process artifacts are missing: no `AGENTS.md`, empty `docs/handoffs/`

- **Severity:** SUGGESTION
- **Where:** repository root; `docs/handoffs/` (exists, empty)
- **Evidence:** The review brief references `AGENTS.md` and `docs/handoffs/CODEX_SLICE_001.md`;
  neither file exists at commit `40ac981`. `docs/SLICE_001_REVIEW.md` (self-review by the
  implementer) exists and its verification numbers were independently confirmed.
- **Why it matters:** If the documented workflow requires an implementation handoff, its
  absence breaks the audit chain the project otherwise builds carefully.
- **Recommended change:** Commit the Codex handoff (or remove references to it from the
  workflow) and add the missing `AGENTS.md` if the contributor process depends on it.
- **Required regression test:** N/A (process artifact).

---

## Positive observations (verified, no action needed)

- **Financial arithmetic and FX direction are correct as implemented:** trusted healthy
  revenue was independently recomputed from raw source data (invoice-date rate lookup,
  `Decimal` multiply, half-up quantize) and matches 916,351.47 exactly; `rate_to_eur`
  direction (EUR per source-currency unit) is consistent everywhere and generator rates are
  realistic (GBP ≈ 1.155, TRY ≈ 0.029).
- **Determinism holds:** byte-identical regeneration confirmed; LF endings enforced on all
  platforms, so fingerprints are cross-platform stable.
- **Interrupted-run recovery is genuinely good:** a simulated crash mid-Silver left no
  state entry; the rerun reprocessed and converged to exactly correct outputs (state-last
  write ordering + per-batch replacement works as designed).
- **Quality vs execution failure separation works** for the covered cases: schema mismatch,
  bad manifest, stale fingerprint raise; rule failures persist evidence and exit 2.
- **Bronze versioning under same-batch corrections works:** both fingerprint versions
  retained, prior Silver contribution replaced (verified by test and rerun probe).
- **`batch_id` is regex-constrained** before being used in paths — no path traversal via
  manifest.
- **Repository hygiene is clean:** 67 tracked files, no generated data, no secrets
  (`.env.example` is names-only), gitignore covers all build/data artifacts, MIT license
  consistent.
- **Cloud honesty is real:** Databricks/Snowflake/Power BI files are explicit
  contracts-only with "not deployed" language; no fake outputs or PBIX; backlog marks them
  PLANNED.

---

## Answers to the five design questions

**1. Withhold one country or reject the whole batch?** Withhold only the incomplete
country partition — the current behavior is right. Countries deliver independently; a
Germany shortfall says nothing about the completeness of the French file, and full-batch
rejection would delay all trusted reporting and multiply steward workload. Two conditions
make it defensible: the FAIL rule row must always be emitted (it is, including for
zero-delivery countries), and the rule must count *distinct* invoices (LIB-R-011). Consider
in a later slice whether the withheld country's *shipments and budgets* should be withheld
with it — today only invoices are held, so operational-vs-invoiced comparisons for that
country are asymmetric.

**2. Which date for invoice translation?** Invoice date, as implemented, is the correct
default for this slice: it is the transaction date under IAS 21 spot-rate translation for
revenue recognized at invoicing, it is deterministic, and it needs no data the slice does
not have. Posting date becomes relevant only when an ERP posting process (and late-posting
scenarios, LIBRA-003) exists; month-end or average rates are management-reporting
conventions that belong in the FX-impact comparison policy, not in base translation.
Record the decision as an ADR requiring finance sign-off, and keep the rate-date selection
a single function so policy can change in one place.

**3. Trust the first duplicate occurrence or withhold all?** Split by conflict. Identical
resends: keep the first, quarantine the rest — the current behavior — because the payloads
agree and withholding would lose real revenue to a transport-layer hiccup. **Conflicting**
duplicates (same ID, different values): withhold *every* occurrence, including the first —
verified behavior today keeps the first value (probe: kept 1,131.62 and quarantined a
99,999.00 later occurrence), yet file order does not prove the first value is the correct
one; a resend is often the correction. For money, ambiguity should mean quarantine, not a
coin-flip on row order.

**4. Is a static country-volume baseline defensible?** Yes, for this slice — with the
docs already saying production needs a trailing-history baseline, the static config is an
honest, reviewable stand-in, and the probe confirmed sane boundary behavior. It becomes
indefensible the moment a second data period exists: fix the duplicate-counting flaw now
(LIB-R-011) so the mechanism is trustworthy, and treat the historical baseline as part of
LIBRA-003 (late arrivals change delivered counts retroactively, which a static threshold
cannot express).

**5. Is local file publication sufficiently safe, and what must Delta guarantee?**
Sufficiently safe for a single-writer local demo, with two caveats proven in this review:
per-file atomicity leaves a window where some datasets carry the new batch and others the
old (crash recovery converges only after a rerun — verified), and the reconciliation
evidence does not currently attest persisted content (LIB-R-003), which is exactly the
blind spot a transactional store is supposed to remove. The future Delta implementation
must guarantee: **(a)** batch publication (Silver replacement + quarantine + quality +
reconciliation + processed-state) commits atomically and serializably per batch — readers
never observe a partially applied batch, and the state flag can never say "processed"
unless the data commit succeeded (commit state *with* the data, not after it); **(b)**
idempotent re-execution keyed on `batch_id` + fingerprint at the transaction level, so a
retried job cannot double-apply; **(c)** post-commit reconciliation reads committed table
versions, not in-memory frames; and **(d)** contribution replacement expressed as a
transactional `MERGE`/`replaceWhere` on `_batch_id` that fails loudly on cross-batch key
ownership changes (LIB-R-002) instead of silently reassigning them.
