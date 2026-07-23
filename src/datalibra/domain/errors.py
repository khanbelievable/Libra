"""Explicit trust-core failures with actionable recovery guidance."""


class StateIntegrityError(RuntimeError):
    """Processed state cannot be used without an explicit recovery action."""


class ClaimsIntegrityError(RuntimeError):
    """Persisted claim evidence failed independent integrity verification."""


class ArtifactIntegrityError(RuntimeError):
    """Committed run evidence is missing or does not match state attestation."""


class CrossBatchCollisionError(RuntimeError):
    """A dataset without claim resolution has a conflicting active owner."""
