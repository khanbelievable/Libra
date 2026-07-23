# ADR-003: Idempotent processing

- **Status:** Accepted
- **Decision:** Identify a delivery by batch ID, content fingerprint, pipeline version,
  data-contract version, and quality-rules fingerprint. Only a fully compatible identity is a
  no-op. A changed payload or processing identity is rebuilt. Invoice business keys are resolved
  across attested batch-owned claims rather than by last-write-wins merge. Ownership uses a
  persisted immutable positive arrival sequence, never JSON member order or batch-ID sorting.
- **Context:** Source resends and retroactive corrections must not duplicate finance results.
- **Consequences:** State and provenance are first-class. Batch IDs are immutable logical
  identities; every distinct payload is retained in Bronze. An exact cross-batch invoice replay
  does not add revenue; conflicting canonical payloads withhold all occurrences until an owning
  batch is corrected. Financial equality includes the normalized source amount, applied FX rate,
  and translated EUR amount as well as invoice dimensions and translation date.

  Each active batch owns an immutable claim manifest. Processed state attests its row count,
  full-row digest, business-key digest, processing identity, and arrival sequence. The aggregate
  claim CSV is a verified, rebuildable index, not the authority.

  Local paths use a checked 80-bit fingerprint prefix to preserve Windows path headroom, while
  the full SHA-256 remains in evidence. Prefix collisions fail loudly. Local publication uses
  atomic file replacement, an inflight recovery marker, committed readback, and state last.
  Exact retries converge after interruption; the marker never represents success. A no-op also
  verifies Silver, quarantine, quality, reconciliation, summary, and claim attestations.

  The production adapter will use a serializable Delta transaction covering claims, trusted data,
  quarantine, quality evidence, reconciliation, summary, and state.
