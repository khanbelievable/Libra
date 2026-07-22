"""Local generation and processing commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from datalibra.generators import generate_scenario
from datalibra.logging import configure_logging
from datalibra.silver import process_batch

BROKEN_SCENARIOS = ("duplicate_invoices", "missing_gbp_fx", "incomplete_germany")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="libra", description="Libra Slice 001 pipeline")
    parser.add_argument("--log-level", default="INFO")
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="Generate deterministic source data")
    generate.add_argument("kind", choices=("healthy", "broken"))
    generate.add_argument("--output", type=Path, default=Path("data/generated"))
    generate.add_argument("--seed", type=int, default=20250101)

    run = commands.add_parser("run", help="Run a generated healthy or broken demo")
    run.add_argument("kind", choices=("healthy", "broken"))
    run.add_argument("--input", type=Path, default=Path("data/generated"))
    run.add_argument("--output", type=Path, default=Path("data/processed"))

    run_batch = commands.add_parser("run-batch", help="Process one batch directory")
    run_batch.add_argument("--batch-dir", type=Path, required=True)
    run_batch.add_argument("--output", type=Path, required=True)
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_logging(args.log_level)
    if args.command == "generate":
        scenarios = ("healthy",) if args.kind == "healthy" else BROKEN_SCENARIOS
        paths = [
            str(generate_scenario(scenario, args.output, seed=args.seed)) for scenario in scenarios
        ]
        _print({"generated": paths, "seed": args.seed})
        return 0
    if args.command == "run-batch":
        summary = process_batch(args.batch_dir, args.output)
        _print(summary.as_dict())
        return 2 if summary.status == "quality_failed" else 0
    scenarios = ("healthy",) if args.kind == "healthy" else BROKEN_SCENARIOS
    summaries = [
        process_batch(args.input / scenario, args.output / scenario).as_dict()
        for scenario in scenarios
    ]
    _print({"runs": summaries})
    return 2 if any(summary["status"] == "quality_failed" for summary in summaries) else 0


if __name__ == "__main__":
    raise SystemExit(main())
