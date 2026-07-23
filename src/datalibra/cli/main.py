"""Local generation and processing commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from datalibra.generators import generate_scenario
from datalibra.logging import configure_logging
from datalibra.orchestration import run_correction_demo, run_local_batch

BROKEN_SCENARIOS = (
    "duplicate_invoices",
    "missing_gbp_fx",
    "incomplete_germany",
    "invalid_operational_costs",
)
CORRECTION_SCENARIOS = ("cost_correction_initial", "cost_correction_corrected")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="libra", description="Libra Milestone 1 pipeline")
    parser.add_argument("--log-level", default="INFO")
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="Generate deterministic source data")
    generate.add_argument("kind", choices=("healthy", "broken", "correction"))
    generate.add_argument("--output", type=Path, default=Path("data/generated"))
    generate.add_argument("--seed", type=int, default=20250101)

    run = commands.add_parser("run", help="Run a generated analytics demo")
    run.add_argument("kind", choices=("healthy", "broken", "correction"))
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
        scenarios = (
            ("healthy",)
            if args.kind == "healthy"
            else (CORRECTION_SCENARIOS if args.kind == "correction" else BROKEN_SCENARIOS)
        )
        paths = [
            str(generate_scenario(scenario, args.output, seed=args.seed)) for scenario in scenarios
        ]
        _print({"generated": paths, "seed": args.seed})
        return 0
    if args.command == "run-batch":
        summary, _ = run_local_batch(args.batch_dir, args.output)
        _print(summary.as_dict())
        return 2 if summary.status == "quality_failed" else 0
    if args.kind == "correction":
        audit = run_correction_demo(args.input, args.output / "correction")
        _print({"correction": audit})
        return 0
    scenarios = ("healthy",) if args.kind == "healthy" else BROKEN_SCENARIOS
    summaries = [
        run_local_batch(args.input / scenario, args.output / scenario)[0].as_dict()
        for scenario in scenarios
    ]
    _print({"runs": summaries})
    return 2 if any(summary["status"] == "quality_failed" for summary in summaries) else 0


if __name__ == "__main__":
    raise SystemExit(main())
