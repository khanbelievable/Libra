# ADR-003: Idempotent processing

- **Status:** Accepted
- **Decision:** Identify a delivery by batch ID plus content fingerprint. Same ID/fingerprint is a no-op. Same ID/new fingerprint is a correction: replace that batch's prior outputs, then merge by business key.
- **Context:** Source resends and retroactive corrections must not duplicate finance results.
- **Consequences:** State and provenance are first-class. Batch IDs are immutable logical identities; every distinct payload is retained in Bronze. Local paths use a checked 80-bit fingerprint prefix to preserve Windows path headroom, while the full SHA-256 remains in evidence. Prefix collisions fail loudly. Silver and quarantine use atomic file replacement locally; processed state is written last. The production adapter will use a serializable Delta transaction covering data and state.
