from __future__ import annotations

import csv
import json
from pathlib import Path

from datalibra.domain.contracts import DATASET_ORDER, SOURCE_FIELDS, source_fingerprint


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_rows(path: Path, dataset: str, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_FIELDS[dataset], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def refresh_manifest(batch_dir: Path) -> None:
    manifest_path = batch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [batch_dir / f"{dataset}.csv" for dataset in DATASET_ORDER]
    for path in paths:
        manifest["datasets"][path.stem] = len(read_rows(path))
    manifest["fingerprint"] = source_fingerprint(paths)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
