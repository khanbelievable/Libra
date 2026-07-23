# ADR-004: Local and cloud adapters

- **Status:** Accepted
- **Decision:** Put shared schemas and finance rules in neutral typed contracts and isolate
  persistence behind one complete, runtime-checkable `PipelineStorage` protocol. CSV is the local
  adapter; PySpark/Delta and Snowflake are optional future adapters.
- **Context:** Contributors need full local tests without Java, cloud credentials, or warehouse access.
- **Consequences:** The protocol covers Bronze, Silver, batch-owned claim manifests, a rebuildable
  claims index, quarantine, quality, state, inflight recovery, summaries, reconciliation, and
  committed reads. `process_batch` accepts an injected adapter.
  Contract fixtures must produce equivalent results across adapters. Platform-specific
  optimizations may differ, but rule names, rounding, ownership, keys, and quarantine semantics
  may not. Every adapter must support post-publication readback and state-last recovery or an
  equivalent atomic transaction.

  Internal adapter records preserve canonical strings exactly, including values beginning with
  spreadsheet formula characters. Formula neutralization belongs to an explicit export helper;
  exported presentation files cannot feed ownership, reconciliation, or replay state.
