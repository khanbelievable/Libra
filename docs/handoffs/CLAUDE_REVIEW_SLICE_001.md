# Claude Independent Review — Slice 001 Handoff

- **Reviewer:** Claude (independent senior data-engineering/architecture review)
- **Date:** 2026-07-22
- **Commit:** `40ac981` on `main`, clean working tree
- **Detailed findings:** `docs/REVIEW_LOG.md` (LIB-R-001 … LIB-R-020)
- **Scope honored:** no production files modified; no Slice 002 work; no cloud work.

---

## 1. Commands executed and exact results

Environment: Windows 11, Python 3.12.10, fresh `.venv` created with the README commands,
`python -m pip install -e ".[dev]"` (install succeeded; mypy 1.20.2, pytest 8.4.2,
pytest-cov 6.3.0, ruff 0.15.22, coverage 7.15.2).

| Command | Result |
|---|---|
| `python -m pytest -q --cov=datalibra --cov-report=term --cov-fail-under=90` | **25 passed**, coverage **94.09 %** (branch-aware) — after redirecting pytest basetemp to a short path; see note below |
| `python -m ruff check .` | All checks passed |
| `python -m ruff format --check .` | 28 files already formatted |
| `python -m mypy src/datalibra` (strict) | Success: no issues found in 19 source files |
| `python -m pip check` | No broken requirements found |
| `libra generate healthy` → `libra run healthy` | exit 0, `status: success`, 720 Silver invoices, revenue `916351.47` |
| `libra run healthy` (rerun, unchanged) | exit 0, `status: already_processed` |
| `libra generate broken` → `libra run broken` | exit 2, three `quality_failed` runs with `DUPLICATE_INVOICE` / `EXCHANGE_RATE_EXISTS` / `INVOICE_COUNTRY_VOLUME` and revenues `916351.47` / `900446.34` / `697854.41` — all matching `demo/expected-results/SLICE_001.md` |

**Environment note (real portability finding):** the first suite run produced 17 errors —
not code defects, but Windows MAX_PATH: pytest's default/deep basetemp plus
`output/bronze/<dataset>/<batch_id>/<64-char-sha256>.csv.tmp` exceeded 260 characters
(measured failing path: 265 chars → `FileNotFoundError`). From a short basetemp everything
passes. Recorded as LIB-R-010.

Beyond the documented gate, ~12 adversarial probe scripts were executed (zero/negative FX
rates, NaN amounts, cross-batch key collisions, lossy/crashing storage adapters, conflicting
FX duplicates, unknown countries, state/summary divergence, CSV injection, volume
boundaries, identical-content resends). Results are embedded per finding in
`docs/REVIEW_LOG.md`.

## 2. Claims independently confirmed

- **"25 tests passing, 94 % branch-aware coverage"** — confirmed exactly (25 passed,
  94.09 % with `branch = true`).
- **mypy strict, ruff lint, ruff format, pip check clean** — confirmed.
- **All four demo scenarios' counts, reason codes, and EUR totals** in README,
  `demo/expected-results/SLICE_001.md`, and `tests/demo` — confirmed by fresh CLI runs.
- **Healthy revenue 916,351.47 is arithmetically correct**, not just self-consistent: I
  recomputed it from the raw generated source files with an independent script
  (invoice-date rate lookup, `Decimal` multiplication, half-up quantization) and matched to
  the cent. Note it is rounding-mode-sensitive (banker's rounding gives …46) — see
  LIB-R-017.
- **FX direction (`rate_to_eur` = EUR per one source-currency unit)** — consistent across
  generator, pipeline, docs; generated rates are realistic for 2025 (GBP≈1.155, TRY≈0.029).
- **Determinism** — same-seed regeneration is byte-identical; LF line endings are forced in
  code (not just `.gitattributes`), so fingerprints are platform-stable.
- **Unchanged rerun is a no-op; changed payload under same batch ID keeps both Bronze
  fingerprint versions and replaces the prior Silver contribution** — confirmed by test and
  by probe.
- **Crash recovery** — a simulated crash after 3 of 8 Silver datasets leaves no state
  entry; rerun converges to exactly correct output (state-written-last ordering works).
- **Quality vs execution failure separation** — rule failures persist evidence and exit 2;
  stale fingerprint/schema mismatch raise (exit 1). Exit-code contract works as documented.
- **Repo hygiene / portfolio honesty** — no secrets, no committed generated data, MIT
  consistent, and the Databricks/Snowflake/Power BI directories are genuinely
  contracts-only with explicit "not deployed" language. Cloud claims are honest.

## 3. Claims not confirmed / contradicted

- **"Reject unsafe records … without inflating revenue" — contradicted in three ways:**
  (a) a `0.000000` or negative FX rate is applied silently: all rules PASS while trusted
  revenue drops from 916,351.47 to 714,544.39 (zero) or 539,944.09 with negative EUR rows
  (negative) — **LIB-R-001, BLOCKER**;
  (b) a second batch ID re-delivering an existing invoice at 10× reaches Silver
  (total inflated to 926,536.05, `DUPLICATE_INVOICE` PASS) and reprocessing the first batch
  then erases the second batch's entire contribution — **LIB-R-002**;
  (c) `NaN` revenue enters Silver and the persisted summary reports revenue `"NaN"` —
  **LIB-R-004**.
- **"Source-to-target row and financial reconciliation" — not a real control.** It compares
  in-memory partitions of one list and cannot fail (probe: storage dropped half of Silver,
  everything still PASS/success). The demo test asserting these rows PASS is asserting a
  tautology — **LIB-R-003**.
- **"Quarantine of … unknown references" (README) — partially true.** Customer, cost
  center, shipment: yes. Country: no — `country_code "XX"` is trusted into Silver
  (**LIB-R-006**). Currency is only indirectly guarded via missing-rate.
- **"Local CSV is an adapter" — aspirational.** The `PipelineStorage` protocol declares 3
  of the 9 methods the pipeline uses, `process_batch` constructs `LocalCsvStorage`
  directly, and the source schema contract is imported from the synthetic-data generator —
  a Delta adapter cannot be slotted in without editing the domain pipeline — **LIB-R-008**.
- **Linux CI results** — not independently re-run here (Windows-only environment); CI badge
  and matrix config reviewed only.
- **`docs/handoffs/CODEX_SLICE_001.md` and `AGENTS.md`** — referenced by the review
  workflow, absent from the repository (**LIB-R-020**).

## 4. Architecture concerns

1. **The storage seam is decorative today** (LIB-R-008): incomplete protocol, hard-wired
   adapter, generator-owned schema, fingerprint logic triplicated (pipeline / generator /
   test helpers). This is the highest-leverage refactor before LIBRA-004.
2. **Merge semantics conflate "correction" with "collision"** (LIB-R-002): batch-scoped
   replacement plus business-key upsert is only safe if batches never share keys, and
   nothing enforces or detects that. The Delta `MERGE` will inherit this design flaw
   verbatim if not fixed at the contract level.
3. **Reconciliation must move from in-memory bookkeeping to persisted attestation**
   (LIB-R-003) — otherwise it will falsely reassure exactly where Delta transactions could
   fail.
4. **Replay identity lacks a pipeline/contract version** (LIB-R-007) — demonstrated live:
   stale outputs on this machine written by an older code version (old Bronze layout) were
   blessed as `already_processed` by today's binary.
5. **Publication-on-quality-failure is intended but under-specified** (LIB-R-016): a batch
   failing a critical rule still merges its valid rows; only the refresh timestamp records
   the difference. Fine as a decision — must be documented as one.
6. Databricks/Snowflake/Power BI responsibility split (ADR-001) is clean and does not
   overlap; contract files are consistent with the docs. No concern there.

## 5. Test gaps (full list in LIB-R-018)

- No unit test of the FX conversion arithmetic or rate-date lookup (no hand-computable
  case like 100.00 GBP × 1.155000 → 115.50); demo totals pin regressions but originate
  from the pipeline's own output.
- `REFERENTIAL_INTEGRITY` FAIL paths (`UNKNOWN_CUSTOMER_ID`, `UNKNOWN_COST_CENTER_ID`,
  `UNKNOWN_SHIPMENT_ID`) never fire in any test.
- No tests for: non-positive/non-finite rates and amounts; conflicting duplicates (same
  invoice ID, different amount); multi-reason rows; budgets quarantine; corrected batch
  replacing prior *quarantine* contribution; volume boundary (72 pass / 71 fail — verified
  by probe, unpinned by tests); cross-batch collisions; `run-batch` CLI; execution-failure
  paths other than stale fingerprint; storage fault injection.
- The demo assertion that `SOURCE_TARGET_*` rows PASS is a false-positive test until
  LIB-R-003 is fixed.

## 6. Required Codex fixes (ordered)

1. **LIB-R-001 (BLOCKER):** `INVALID_EXCHANGE_RATE` rule — reject non-finite and ≤ 0 rates;
   quarantine dependent facts; regression tests for zero/negative/non-finite.
2. **LIB-R-004:** reject non-finite amounts (`INVALID_AMOUNT` reason); `decimal_string`
   asserts finiteness; tests for NaN/Infinity/sNaN.
3. **LIB-R-002:** cross-batch business-key collision detection (quarantine or explicit
   supersession + overwrite audit); two-batch regression tests including the
   reprocess-ping-pong case.
4. **LIB-R-003:** reconciliation recomputed from persisted files post-publication; lossy-
   adapter fault-injection test.
5. **LIB-R-005:** business-key uniqueness enforcement for all datasets; conflicting
   reference-data duplicates fail a critical rule.
6. **LIB-R-006:** `UNKNOWN_COUNTRY_CODE` (and optionally unknown-currency) referential
   check.
7. **LIB-R-007:** `pipeline_version` in state/summaries; version mismatch forces
   reprocessing.
8. **LIB-R-008:** complete `PipelineStorage`, inject it into `process_batch`, move `FIELDS`
   + fingerprint into a neutral schema/contract module.
9. **MINORs:** LIB-R-009 … LIB-R-018 as capacity allows — prioritize LIB-R-011
   (duplicate-counting volume rule) and LIB-R-013 (replay crash) since both touch trust
   semantics; document decisions for LIB-R-016 and LIB-R-017.

## 7. Recommended next slice — only after the fixes above

Hold LIBRA-002 (routes/operational costs) until items 1–8 land with their regression
tests. The findings are all in the trust core (rates, merge, reconciliation, replay
identity); building more fact types on top would replicate the same weaknesses into the
cost pipeline. After the fixes, LIBRA-002 as scoped in the backlog is the right next slice,
with one addition: implement the storage-seam refactor (item 8) *before* adding new
datasets, so route/cost processing is written against the real adapter interface from day
one and LIBRA-004 (Delta) does not require rewriting freshly written code.

---

## Verdict

**CHANGES REQUIRED**
