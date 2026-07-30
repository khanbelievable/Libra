-- Run with a role allowed to inspect grants. Loader must have no REPORTING access.
SHOW GRANTS TO ROLE LIBRA_LOADER;
SHOW GRANTS TO ROLE LIBRA_FINANCE_READER;
SHOW GRANTS TO ROLE LIBRA_DQ_READER;

-- Expected:
-- LIBRA_LOADER: CONTROL/LOAD only plus the owner-executed publish procedure.
-- LIBRA_FINANCE_READER: approved finance REPORTING views only.
-- LIBRA_DQ_READER: DQ, refresh, and reconciliation REPORTING views only.
-- Neither reader role may own or modify CONTROL, LOAD, or CORE objects.
