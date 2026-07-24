import pytest

from datalibra.databricks.delta import _replacement_owner_ids
from datalibra.databricks.tasks import _superseded_batch_id


def test_replacement_owner_ids_are_narrowly_scoped() -> None:
    assert _replacement_owner_ids("current", None) == ("current",)
    assert _replacement_owner_ids("current", "prior") == ("current", "prior")


def test_supersession_rejects_self_and_unsafe_identifiers() -> None:
    with pytest.raises(ValueError, match="another batch"):
        _superseded_batch_id({"supersedes_batch_id": "current"}, "current")
    with pytest.raises(ValueError, match="invalid"):
        _superseded_batch_id({"supersedes_batch_id": "../prior"}, "current")
