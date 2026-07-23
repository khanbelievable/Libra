# ADR-001: Platform responsibilities

- **Status:** Accepted
- **Decision:** Databricks/Delta owns ingestion, cleansing, deduplication, FX normalization, quality/quarantine, and finance aggregates. Snowflake owns governed dimensional serving, secure marts/views, load audit, and role-based access. Power BI owns semantic relationships, reusable DAX, navigation, and visualization.
- **Context:** Repeating transformations in Databricks and Snowflake would create competing answers and increase reconciliation cost.
- **Consequences:** Gold-to-Snowflake contracts must be versioned. Snowflake may validate but
  does not reinterpret finance logic. Milestone 1 implements the Databricks responsibility with
  PySpark/Delta and retains the local pipeline as its deterministic financial oracle. Deployment
  status is evidenced separately from source-code completion.
