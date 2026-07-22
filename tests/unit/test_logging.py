from __future__ import annotations

import json
import logging

from datalibra.logging import JsonFormatter


def test_json_formatter_includes_pipeline_context() -> None:
    record = logging.LogRecord(
        name="datalibra.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Batch complete",
        args=(),
        exc_info=None,
    )
    record.batch_id = "slice001-healthy"  # type: ignore[attr-defined]
    record.status = "success"  # type: ignore[attr-defined]

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["message"] == "Batch complete"
    assert payload["batch_id"] == "slice001-healthy"
    assert payload["status"] == "success"
    assert payload["timestamp"].endswith("+00:00")
