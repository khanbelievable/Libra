# Claude Independent Re-Review — Slice 001.1 Handoff

- **Reviewer:** Claude (independent senior data-engineering/architecture review)
- **Date:** 2026-07-22
- **Commit re-reviewed:** `54748ff01f07ad1e33c859bd11fced3ad189fffa` (`main`, clean tree)
- **Baseline:** `40ac981`; all 13 remediation commits inspected (`40ac981..54748ff`), history
  coherent, remediation implemented in production code (not only tests/docs): contracts module,
  storage protocol, pipeline validation/claims/reconciliation, packaging, and config loader all
  changed substantively.
- **Detailed findings:** `docs/RE_REVIEW_SLICE_001_1.md` (original findings + LIB-RR-001…010)
- **Scope honored:** no production code modified; no fixes implemented; no Slice 002 work.

## 1. Environment and exact commands

Windows 11, Python 3.12.10. Fresh `.venv-rereview` (editable install) plus a second clean venv
for the out-of-checkout wheel test. Tool versions: pytest 8.4.2, pytest-cov 6.3.0,
coverage 7.15.2, ruff 0.15.22, mypy 1.20.2.

| Command | Result |
|---|---|
| `python -m pip install -e ".[dev]"` | success |
| `python -m pytest -q --cov=datalibra --cov-report=term --cov-branch --cov-fail-under=90` | **81 passed, 1 failed**, 86.2 s; coverage **96.91 %** (785 stmts, 218 branches) |
| `python -m ruff check .` | All checks passed |
| `python -m ruff format --check .` | 39 files already formatted |
| `python -m mypy src/datalibra` (strict) | Success: no issues found in 21 source files |
| `python -m pip check` | No broken requirements found |
| `python -m pip wheel . --no-deps --wheel-dir …` | Built `datalibra-0.1.1-py3-none-any.whl` (29,275 bytes; sha256 `b4fdf3a1…` — build-env-specific, differs from Codex's recorded hash as expected) |
| Wheel install in clean venv, neutral directory | success |
| `libra generate healthy` / `libra run healthy` (outside checkout) | exit 0 / exit 0, `success`, 720 invoices, EUR 916,351.47 |
| `libra run healthy` rerun | exit 0, `already_processed` |
| `libra generate broken` / `libra run broken` (outside checkout) | exit 0 / exit 2; `quality_failed` ×3 with revenues 916,351.47 / 900,446.34 / 697,854.41 |

**The one test failure** is `test_deep_output_root_stays_below_practical_windows_path_limit`:
`assert 242 < 240`. The pipeline run inside the test **succeeded** at a 166-character root; the
test's own margin arithmetic depends on the temp-root length modulo 22 and fails for ~3/22 of
possible basetemp lengths (LIB-RR-003). So the claimed "82 passed" reproduces only in
environments whose temp path happens to land inside the margin; the product behavior it guards
is fine. No pytest warnings beyond this failure.

Output evidence inspected after the CLI runs: Bronze flat short-ID files, `claims/`, Silver,
quarantine (all eight datasets), quality results, reconciliation JSON with committed-readback
fields (`committed_batch_trusted_rows/eur`, `global_business_keys_match`,
`quarantine_evidence_matches`), versioned run summary (`pipeline_version 0.1.1`,
`data_contract_version 1.1`, rules SHA-256), versioned state, correct watermark.

Roughly a dozen adversarial probe scripts were executed beyond the gate; transcripts are
summarized per finding in `docs/RE_REVIEW_SLICE_001_1.md`.

## 2. Independently confirmed

- **Coverage and gates:** 96.91 % branch coverage (matches claim); ruff/mypy/pip check clean;
  mypy 21 files (matches). Test count claim of 82 passing is **environment-sensitive** (81+1
  here).
- **Packaging:** wheel contains `config_defaults`; installed CLI fully works outside the
  checkout, healthy and broken paths, correct exit codes (LIB-R-015 closed). CI extends to
  wheel install + out-of-checkout smoke.
- **All original BLOCKER/MAJOR exploits re-attempted:** zero/negative/NaN/Infinity/malformed
  FX rates, NaN/sNaN/±Infinity/malformed/negative amounts, exact and 10×-conflicting
  cross-batch redelivery in both orders, batch-A-replay-erases-batch-B, lossy/altering/omitting
  /duplicating/stale/quarantine-dropping storage adapters, stale-version and missing-summary
  replay, deep paths, formula injection — none of the original failures reproduces.
- **Reconciliation is genuinely committed-readback:** 6 of 7 injected storage corruptions are
  detected with critical FAILs and a held watermark (the 7th — dropped quality evidence — is
  the new MINOR LIB-RR-004).
- **Storage seam is real:** complete protocol (all 14 orchestration calls declared), injected
  adapter, neutral contracts; my own protocol-only in-memory adapter runs the full pipeline,
  replay, and dedup correctly.
- **Determinism:** two identical healthy runs produce byte-identical output trees; volume rule
  counts distinct invoices (72 passes / 71 fails / 50+30 duplicates fails); corrections clear
  stale quarantine and quality failures and advance the watermark correctly; interrupted
  publication and state loss recover by replay; two sequential corrections converge with all
  Bronze versions retained; no Git executable is needed at runtime.

## 3. Not confirmed / contradicted

- **"Exact redelivery keeps the earliest active owner" — contradicted.** Ownership rank is
  taken from the state file's key order, which `write_json_atomic(sort_keys=True)`
  alphabetizes. A later, unrelated run re-resolves claims in alphabetical order and silently
  flips ownership; with rate-divergent "exact" replays the trusted total changed
  916,351.47 → 933,811.44 on a green run (**LIB-RR-001, MAJOR** — makes LIB-R-002
  PARTIALLY CLOSED).
- **"Reconciliation … detects every corruption" — one class escapes.** Loss of the `claims/`
  store (now the de-facto system of record for Silver invoices) silently erases all previously
  trusted invoices; the next run reports success and every reconciliation row passes
  (**LIB-RR-002, MAJOR**).
- **"82 passed" — environment-dependent** (brittle path-guard test, LIB-RR-003).
- Minor residuals: no-op replay doesn't check committed output exists (LIB-RR-005);
  spreadsheet neutralization mutates stored keys and can raise false reconciliation failures
  (LIB-RR-006); non-invoice facts remain cross-batch last-write-wins (LIB-RR-007); malformed
  state crashes raw (LIB-RR-008).

## 4. Architecture assessment

The remediation is a real architectural upgrade, not test decoration: neutral contracts,
complete injectable storage protocol, validation-first standardization, claims-based global
invoice resolution, committed-readback attestation, versioned replay identity, state-last
recovery. The two MAJOR regressions share one root theme: **the claims mechanism introduced a
new global system of record without giving it the same rigor as the rest of the trust core** —
its ordering source is accidental (JSON key order) and its durability is unattested. Both
fixes are small and local (persist an explicit arrival sequence; cross-check claims against
processed state; treat amount-divergent replays as conflicts). The single-writer scope is
honestly documented; the Delta contract requires serializable publication (add reconciliation
and summaries to its listed scope — LIB-RR-009).

## 5. Portfolio-honesty assessment

- Databricks/Delta, Snowflake, Power BI: consistently presented as contracts/planned; "not
  deployed" language intact in all three trees; no fake outputs; local adapter never described
  as a cloud integration. Backlog gates Slice 002 on this re-review.
- Test/coverage claims: coverage and gates match; the test-count claim needs the LIB-RR-003
  fix to be robustly true. README's behavior claims ("cross-batch invoice ownership that
  prevents redelivery inflation", "post-publication reconciliation") are supported by my
  probes, with the two documented exceptions (LIB-RR-001/002) — the "earliest active owner"
  wording in docs is currently stronger than the implementation.
- Naming: project consistently "Libra"; one residual `DataLibraFinance` in
  `powerbi/README.md:7` (LIB-RR-010, SUGGESTION).

## 6. May Slice 002 begin?

**No.** Two newly discovered MAJOR defects sit in the trust core that Slice 002 would build
on, and one original MAJOR (LIB-R-002) is therefore only partially closed. Everything else —
including every original BLOCKER exploit — is independently verified closed.

### Required fixes before Slice 002

1. **LIB-RR-001 (MAJOR):** rank invoice claims by a persisted monotonic arrival sequence, not
   JSON key order; classify canonically-identical claims with differing `amount_eur` as
   conflicts; add three-batch ownership-stability and rate-divergent-replay regression tests.
2. **LIB-RR-002 (MAJOR):** attest claims against processed state (a state-recorded trusted
   contribution missing from claims must fail reconciliation, not shrink Silver); document
   `claims/` as trust-critical evidence with a lifecycle policy; add claims-loss regression
   tests.
3. **LIB-RR-003 (MINOR, required because it breaks the quality gate's portability):** make the
   deep-path guard test deterministic in its constructed root length.
4. Recommended alongside (not gating): LIB-RR-004…007 dispositions — fix or explicitly
   document each.

After 1–3 land with tests, re-verification can be narrow: rerun the cross-batch and claims
probes plus the full gate; the remaining verified-closed findings do not need re-execution.

---

## Verdict

**CHANGES REQUIRED — SLICE 002 MUST NOT BEGIN**
