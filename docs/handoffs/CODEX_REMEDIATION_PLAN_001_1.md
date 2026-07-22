# Slice 001.1 Trust Core Remediation Plan

- **Scope:** Slice 001.1 only
- **Review baseline:** `40ac981`
- **Source review:** `docs/REVIEW_LOG.md` and `docs/handoffs/CLAUDE_REVIEW_SLICE_001.md`
- **Implementation rule:** No Slice 002 datasets, cloud deployments, or Power BI implementation

## BLOCKER and MAJOR findings

| Finding | Review summary | Affected implementation/files | Intended behavior | Required regression evidence |
|---|---|---|---|---|
| **LIB-R-001 — BLOCKER** | Existing FX rows are treated as usable without checking sign or finiteness. Zero and negative GBP rates enter Silver and silently reduce or invert EUR revenue while every rule passes. | `domain/normalization.py`; new neutral domain contracts; `silver/pipeline.py`; `quality/rules.py`; quality config; FX integration tests | An FX rate must be a finite decimal strictly greater than zero. Malformed, zero, negative, NaN, and infinite rates are quarantined as reference-data failures. Their `(date, currency)` key is unavailable to conversion, so dependent facts are quarantined with an explicit invalid/conflicting-rate reason and no EUR value. | Zero GBP; negative GBP; `NaN`, `sNaN`, `Infinity`, `-Infinity`; malformed rate; missing rate. Assert reference quarantine, dependent fact quarantine, critical FAIL results, numeric summaries, and no affected transaction in trusted Silver. |
| **LIB-R-002 — MAJOR** | Invoice uniqueness is checked only inside one file. A second batch can silently take ownership of an invoice key, inflate revenue, and later be erased by replaying the first batch. | `silver/pipeline.py`; storage contract and local adapter; invoice canonical-payload helper; ADR-003; cross-batch integration tests | Compare incoming invoices with committed invoices from other active batches before publication. Identical canonical payloads are cross-batch replays: do not add another trusted row and retain explicit duplicate evidence. Conflicting payloads with the same invoice key withhold every occurrence from trusted Silver until resolved. Batch replacement removes/replaces only rows owned by that batch and never unrelated rows. | Second batch exact resend cannot inflate revenue; ten-times amount conflict is untrusted; replaying batch A preserves unrelated batch B keys; correcting A changes only A-owned evidence; exact cross-batch replay stays idempotent; conflict resolution restores the unique surviving canonical invoice. |
| **LIB-R-003 — MAJOR** | Reconciliation compares in-memory partitions of the same rows before storage writes, so it cannot attest persisted output. | Complete `PipelineStorage`; `storage/local.py`; new reconciliation module or pipeline phase; fault-injection test adapter; demo assertions | Publish candidate Silver/quarantine, then read committed rows through the storage interface. Reconcile committed row counts, business keys, batch-owned contributions, and financial totals against intended post-commit state. A mismatch emits critical reconciliation failures, marks the run untrusted, writes state last, and never reports the intended in-memory counts as committed facts. | Storage adapter drops half of Silver; alters one committed amount; omits one batch contribution. Each must fail the appropriate committed row/key/amount/contribution reconciliation. Healthy and controlled DQ scenarios must pass read-back reconciliation. |
| **LIB-R-004 — MAJOR** | `Decimal` accepts NaN and infinity; non-finite amounts can enter Silver and poison totals/summaries with `"NaN"`. | `domain/normalization.py`; fact standardization/validation; `quality/rules.py`; monetary boundary tests | Every trusted monetary/quantity value must parse as a finite decimal. Malformed and non-finite values become row-level `INVALID_FINANCIAL_VALUE` quarantine evidence. Domain-forbidden negative revenue/budget values are rejected. `decimal_string`, sums, summaries, and reconciliation must refuse non-finite values. | `NaN`, `sNaN`, positive/negative infinity, malformed strings, negative revenue, negative budget, zero boundaries, and hand-computable FX conversion. Assert no non-finite persisted summaries or reconciliation fields. |
| **LIB-R-005 — MAJOR** | Duplicate `(rate_date, currency)` rows silently use the last rate. A conflicting duplicate can arbitrarily control every dependent EUR value. | Neutral dataset contracts; FX validation/deduplication phase; pipeline; reference quarantine; rule config/docs; FX duplicate tests | Canonical exact duplicates with the same normalized rate collapse deterministically to one trusted rate. Conflicting duplicates quarantine every occurrence for that key, publish no trusted rate for the key, and quarantine dependent facts with `CONFLICTING_EXCHANGE_RATE`. No last-write-wins behavior. | Identical duplicate rate deduplicates safely; conflicting duplicate fails a critical rule; neither contested rate enters Silver; dependent facts remain untrusted; committed totals cannot silently change. |
| **LIB-R-006 — MAJOR** | Country references are not checked; unknown country values reach Silver. Currency values are only indirectly reported as missing rates. | Pipeline reference validation; neutral contracts; `quality/rules.py`; reference integrity tests; acceptance/quality docs | Validate every configured Slice 001 reference used by trusted facts/dimensions: country, currency, customer, cost center, and shipment. Emit precise `UNKNOWN_*` reason codes. Unknown reference rows do not enter trusted Silver. | Separate tests for unknown country, currency, customer, cost center, and shipment; dimension-to-country/default-currency checks; multi-reason row; affected budgets and shipments. |
| **LIB-R-007 — MAJOR** | No-op replay uses only batch ID + source fingerprint, so stale outputs from an older pipeline or contract are blessed as current. | New version/contracts module; configuration version/fingerprint; summary/state models; pipeline no-op policy; state tests; ADR-003 | Persist explicit `pipeline_version`, `data_contract_version`, and deterministic `quality_rules_version`. No-op is permitted only when the batch fingerprint and all compatibility versions match and required evidence exists. Missing/older/incompatible state forces safe reprocessing; no Git executable is required. | Old pipeline marker, old contract marker, changed rules fingerprint, missing summary, and matching versions. Assert mismatches reprocess; compatible unchanged input returns `already_processed`. |
| **LIB-R-008 — MAJOR** | The storage protocol declares only three of the methods actually used, the pipeline constructs the CSV adapter directly, and schemas/fingerprint logic are owned or duplicated by generator/test code. | `storage/base.py`; `storage/local.py`; `silver/pipeline.py`; new `domain/contracts.py`; generator and test helpers; adapter contract tests | Define one complete, runtime-independent storage protocol covering Bronze, Silver, quarantine, quality, reconciliation, summaries, state, committed reads, batch-owned replacement, and recovery ordering. Inject the protocol into `process_batch`, using `LocalCsvStorage` only as a default factory. Move source schemas, business keys where appropriate, version constants, canonical fingerprint, and canonical payload definitions into neutral domain contracts. | Run the pipeline through a second test adapter/fault wrapper without editing production orchestration; protocol conformance/type check; canonical fingerprint shared by generator, pipeline, and tests; interrupted publication leaves state absent and rerun converges. |

## Required remediation beyond review severity

### Windows path length

LIB-R-010 is MINOR in the review but mandatory in this remediation brief. Bronze will use a flat path with a short content identifier derived from the full SHA-256 fingerprint. The full fingerprint remains in manifest, row provenance, summary, and state. The initial collision strategy is a 20-hex-character (80-bit) prefix plus an explicit check that an existing short-ID file contains the same full fingerprint; a mismatch fails loudly instead of overwriting evidence. A Windows-oriented test will process beneath a deliberately deep root and assert practical write paths remain below the classic limit.

### Workflow artifacts

Create `AGENTS.md`, restore `docs/handoffs/CODEX_SLICE_001.md` as an accurate historical handoff, retain the Claude review, add remediation links to `docs/README.md`, and create the final Slice 001.1 handoff. These names are explicitly required by the current review workflow even though the earlier public-profile cleanup intentionally removed tool-specific files.

### Atomicity and crash recovery

The local adapter remains single-writer and state-written-last. Candidate outputs and evidence are written before batch state. Missing or incompatible evidence forces replay. Fault tests will interrupt publication and verify state never claims a completed batch. The future Delta contract will require a serializable atomic commit of trusted data, quarantine, quality evidence, reconciliation, and processed state (or an equivalent transaction protocol).

## Contradictory or ambiguous recommendations

1. **Invalid-rate plausibility bands:** Claude suggests optionally rejecting an “absurd magnitude,” but the remediation acceptance criteria require malformed/non-finite/non-positive rates, not currency-specific market bands. A hard-coded plausibility band could reject legitimate TRY/GBP regime changes. This slice will enforce finite and `> 0`; plausibility thresholds remain a separately approved/configured finance policy.
2. **Cross-batch duplicate policy:** Claude initially offers quarantining only the incoming collision or explicit supersession. The remediation brief and Claude’s design answer are stricter for conflicting payloads: withhold all occurrences. The stricter rule governs Slice 001.1.
3. **Quality-failed publication:** Existing demos publish valid rows from a batch with row-level failures. This remains allowed, but committed reconciliation and batch status must make the trust boundary explicit. Conflicting invoice keys and invalid FX dependencies are never considered valid rows.
4. **Exact duplicate evidence grain:** LIB-R-012 notes that per-batch quarantine can double-count an upstream event. Audit evidence will remain per batch because deliveries are distinct audit events; steward metrics must use distinct business key/reason where cross-batch event counts are needed.
5. **Public provenance vs required workflow files:** The previous repository cleanup removed assistant-specific artifacts. The current brief explicitly requires `AGENTS.md` and Codex-named handoffs. They will be concise, factual engineering records with no unsupported authorship claims.
6. **State on committed corruption:** The brief allows failing the run or marking it untrusted. The chosen behavior is a completed `quality_failed` run with critical reconciliation results and state written last; it must never advance the latest successful refresh. Execution/storage exceptions still raise and write no state.

## Planned commit sequence

Each commit will include its direct regression tests and leave the repository passing.

1. **`refactor(contracts): centralize dataset and storage contracts`**  
   Move dataset schemas/fingerprinting/version definitions to neutral domain contracts, complete and inject `PipelineStorage`, and prove the alternate-adapter seam.
2. **`fix(paths): shorten immutable Bronze evidence paths`**  
   Add the flat short-ID Bronze layout, full-fingerprint collision check, deep Windows path regression, and recovery documentation.
3. **`fix(validation): reject unsafe financial and reference values`**  
   Add finite/positive FX validation, finite/domain-valid money validation, precise reference checks, quarantine semantics, and boundary/malformed tests.
4. **`fix(quality): detect conflicting FX reference records`**  
   Deterministically collapse exact FX duplicates, withhold conflicting keys and dependent facts, and test both cases.
5. **`fix(dedup): enforce cross-batch invoice uniqueness`**  
   Add canonical payload comparison, exact replay handling, all-occurrence conflict withholding, batch ownership isolation, correction resolution, and multi-batch tests.
6. **`fix(reconciliation): attest committed storage outputs`**  
   Read back committed rows/keys/amounts/contributions, add fault-injection adapters, make mismatches critical, and preserve state-written-last recovery.
7. **`fix(state): version replay compatibility`**  
   Stamp pipeline/data-contract/rules versions, force replay for incompatible or incomplete evidence, and test missing-summary/stale-version recovery.
8. **`docs: close Slice 001.1 review findings`**  
   Update review status, acceptance criteria, rules, architecture, ADRs, backlog, README, workflow artifacts, and final handoff with exact commits/results.

Commit grouping may be consolidated only when two changes cannot remain valid independently; cosmetic-only commits will not be created.

## Completion gate

- All BLOCKER/MAJOR regression tests pass, including adversarial storage faults.
- Existing healthy/broken scenario contracts remain intentionally stable or documented where trust semantics require a change.
- Full pytest and branch coverage, Ruff lint/format, strict mypy, `pip check`, wheel/clean-install smoke, and all CLI demos pass.
- Review log records the disposition and evidence for every finding.
- No Slice 002 or cloud deployment work is present.
