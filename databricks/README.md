# Databricks interface — not deployed in Slice 001

Databricks is the approved production transformation plane. Slice 001 intentionally ships no pretend notebook outputs or unverified workspace deployment. The local `PipelineStorage` protocol and domain contract define the behavior the Delta adapter must preserve.

The next Databricks slice will provide:

- Auto Loader or batch landing into append-only Bronze Delta tables with `_batch_id`, source path/row, ingestion timestamp, and payload fingerprint.
- PySpark DataFrame standardization equivalent to the local rules, using explicit schemas and `DecimalType`.
- Silver Delta `MERGE` keyed by the keys in `config/datasets/slice_001.json`.
- Quarantine and quality-result Delta tables with the stable reason codes in `docs/DATA_QUALITY_RULES.md`.
- Gold finance exports conforming to `databricks/sql/GOLD_EXPORT_CONTRACT.sql`.
- Asset Bundle validation and a real workspace smoke run before the adapter is called complete.

This boundary is intentional: local tests require neither Java nor a Databricks credential, and cloud-specific imports must remain lazy.
