from __future__ import annotations

import json
from pathlib import Path

import pytest

from datalibra.cli.main import main


@pytest.mark.integration
def test_cli_healthy_workflow_and_idempotent_rerun(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generated = tmp_path / "generated"
    processed = tmp_path / "processed"

    assert main(["generate", "healthy", "--output", str(generated)]) == 0
    generation = json.loads(capsys.readouterr().out)
    assert generation["seed"] == 20250101
    assert generation["generated"] == [str(generated / "healthy")]

    assert (
        main(
            [
                "run",
                "healthy",
                "--input",
                str(generated),
                "--output",
                str(processed),
            ]
        )
        == 0
    )
    first_run = json.loads(capsys.readouterr().out)["runs"][0]
    assert first_run["status"] == "success"
    assert first_run["trusted_invoice_revenue_eur"] == "916351.47"

    assert (
        main(
            [
                "run",
                "healthy",
                "--input",
                str(generated),
                "--output",
                str(processed),
            ]
        )
        == 0
    )
    rerun = json.loads(capsys.readouterr().out)["runs"][0]
    assert rerun["status"] == "already_processed"


@pytest.mark.integration
def test_cli_broken_workflow_returns_controlled_quality_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generated = tmp_path / "generated"
    processed = tmp_path / "processed"

    assert main(["generate", "broken", "--output", str(generated)]) == 0
    capsys.readouterr()
    exit_code = main(
        [
            "run",
            "broken",
            "--input",
            str(generated),
            "--output",
            str(processed),
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert [run["status"] for run in result["runs"]] == [
        "quality_failed",
        "quality_failed",
        "quality_failed",
        "quality_failed",
    ]
    assert [run["failed_rules"] for run in result["runs"]] == [
        ["DUPLICATE_INVOICE"],
        ["EXCHANGE_RATE_EXISTS"],
        ["INVOICE_COUNTRY_VOLUME"],
        [
            "EXCHANGE_RATE_EXISTS",
            "FINITE_FINANCIAL_VALUES",
            "REFERENTIAL_INTEGRITY",
            "VALID_COST_TYPE",
        ],
    ]


@pytest.mark.integration
def test_cli_correction_workflow_reports_owner_scoped_history_change(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generated = tmp_path / "generated"
    processed = tmp_path / "processed"

    assert main(["generate", "correction", "--output", str(generated)]) == 0
    generation = json.loads(capsys.readouterr().out)
    assert generation["generated"] == [
        str(generated / "cost_correction_initial"),
        str(generated / "cost_correction_corrected"),
    ]

    assert (
        main(
            [
                "run",
                "correction",
                "--input",
                str(generated),
                "--output",
                str(processed),
            ]
        )
        == 0
    )
    correction = json.loads(capsys.readouterr().out)["correction"]
    assert correction["batch_id"] == "milestone1-correction"
    assert correction["arrival_sequence"] == 1
    assert correction["initial"]["operational_cost_rows"] == 2879
    assert correction["corrected"]["operational_cost_rows"] == 2880
    assert correction["trusted_cost_ids_are_unique"]
