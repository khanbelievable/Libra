# Snowflake serving contract — not deployed in Slice 001

Snowflake is the governed reporting warehouse, not a second transformation engine. It will receive conformed Databricks Gold exports, enforce versioned load contracts, create warehouse surrogate keys/history where approved, publish finance marts, retain load/reconciliation audits, and apply least-privilege roles.

No credentials, connection attempt, migration execution, or claimed Snowflake test is part of Slice 001. Planned objects are listed in `schemas/FINANCE_STAR_CONTRACT.md`; role boundaries are in `security/ROLE_MODEL.md`. LIBRA-005 owns executable migrations and cloud evidence.
