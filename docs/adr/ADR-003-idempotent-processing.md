# ADR-003: Idempotent processing

- **Status:** Accepted
- **Decision:** Identify a delivery by batch ID, content fingerprint, pipeline version,
  data-contract version, and quality-rules fingerprint. Only a fully compatible identity is a
  no-op. A changed payload or processing identity is rebuilt. Invoice business keys are resolved
  across active batch-owned claims rather than by last-write-wins merge.
- **Context:** Source resends and retroactive corrections must not duplicate finance results.
- **Consequences:** State and provenance are first-class. Batch IDs are immutable logical
  identities; every distinct payload is retained in Bronze. An exact cross-batch invoice replay
  does not add revenue; conflicting canonical payloads withhold all occurrences until an owning
  batch is corrected. Local paths use a checked 80-bit fingerprint prefix to preserve Windows
  path headroom, while the full SHA-256 remains in evidence. Prefix collisions fail loudly.
  Silver and quarantine use atomic file replacement locally; processed state is written last.
  Missing summaries self-heal by replay. The production adapter will use a serializable Delta
  transaction covering trusted data, quarantine, quality evidence, and state.
