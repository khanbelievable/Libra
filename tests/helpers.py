from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from datalibra.generators.synthetic import DATASET_ORDER, FIELDS


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_rows(path: Path, dataset: str, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS[dataset], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def refresh_manifest(batch_dir: Path) -> None:
    manifest_path = batch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    for path in sorted(
        (batch_dir / f"{dataset}.csv" for dataset in DATASET_ORDER),
        key=lambda item: item.name,
    ):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
        manifest["datasets"][path.stem] = len(read_rows(path))
    manifest["fingerprint"] = digest.hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
