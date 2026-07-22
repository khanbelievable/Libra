# ADR-002: Medallion architecture

- **Status:** Accepted
- **Decision:** Preserve source evidence in Bronze, keep conformed trusted records in Silver, and publish purpose-built finance aggregates in Gold.
- **Context:** Auditability and replay require separation between received values and trusted reporting data.
- **Consequences:** Bronze includes provenance and remains replayable. Invalid rows go to quarantine, never Silver. Gold is introduced only with real aggregate use cases, not empty tables.
