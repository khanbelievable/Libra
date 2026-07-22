# ADR-003: Idempotent processing

- **Status:** Accepted
- **Decision:** Identify a delivery by batch ID plus content fingerprint. Same ID/fingerprint is a no-op. Same ID/new fingerprint is a correction: replace that batch's prior outputs, then merge by business key.
- **Context:** Source resends and retroactive corrections must not duplicate finance results.
- **Consequences:** State and provenance are first-class. Batch IDs are immutable logical identities; every distinct payload is retained in Bronze under its fingerprint. Silver and quarantine use atomic file replacement locally, while the production adapter will use Delta transactions.
