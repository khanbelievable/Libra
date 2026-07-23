# Contributing

Libra is developed in small vertical slices. A change should leave behind executable evidence, not just a new interface or diagram.

## Development setup

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

Activate `.venv` using the command appropriate for your shell, then run:

```bash
python -m pytest -q --cov=datalibra --cov-report=term --cov-fail-under=90
python -m ruff check .
python -m ruff format --check .
python -m mypy src/datalibra
python -m pip check
```

## Engineering rules

- Target Python 3.12 and type public functions.
- Use `Decimal` for persisted finance values.
- Keep source evidence immutable and keep invalid records out of Silver.
- Add stable, human-readable reason codes for new quarantine behavior.
- Preserve idempotency for unchanged and corrected batches.
- Preserve immutable arrival order, batch-owned claim evidence, and state-last publication.
- Keep internal CSV values canonical; formula-safe spreadsheet files are presentation exports,
  not pipeline inputs.
- Put business thresholds and dataset keys in version-controlled configuration.
- Keep cloud SDK imports behind adapters so local tests need no credentials.
- Update the relevant ADR, quality rule, KPI definition, or data model when behavior changes.
- Add unit coverage for rules and integration/demo evidence for business outcomes.

Generated data, credentials, local environments, and processing output must not be committed.

## Change checklist

1. Keep the change within one backlog outcome.
2. Add or update tests before changing completion status.
3. Run the complete local verification gate.
4. Confirm the README commands still work from a clean environment.
5. Record material design trade-offs in an ADR.
6. For packaging changes, install the built wheel and run the CLI outside the checkout.
