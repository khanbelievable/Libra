# ADR-004: Local and cloud adapters

- **Status:** Accepted
- **Decision:** Put finance rules in typed, deterministic domain functions and isolate persistence/orchestration adapters. CSV is the local adapter; PySpark/Delta and Snowflake are optional production adapters.
- **Context:** Contributors need full local tests without Java, cloud credentials, or warehouse access.
- **Consequences:** Contract fixtures must produce equivalent results across adapters. Optional packages are lazy imports. Platform-specific optimizations may differ, but rule names, rounding, keys, and quarantine semantics may not.
