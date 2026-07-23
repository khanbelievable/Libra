from __future__ import annotations

from pathlib import Path

import yaml


def test_bundle_declares_one_three_task_serverless_wheel_job() -> None:
    root = Path(__file__).parents[2]
    bundle = yaml.safe_load((root / "databricks.yml").read_text(encoding="utf-8"))
    resources = yaml.safe_load(
        (root / "databricks" / "resources" / "libra_job.yml").read_text(encoding="utf-8")
    )

    assert bundle["bundle"]["name"] == "libra-milestone-1"
    assert bundle["artifacts"]["default"]["type"] == "whl"
    jobs = resources["resources"]["jobs"]
    assert list(jobs) == ["milestone_1"]
    job = jobs["milestone_1"]
    tasks = job["tasks"]
    assert [task["task_key"] for task in tasks] == [
        "land_bronze",
        "build_silver",
        "build_gold_and_validate",
    ]
    assert tasks[1]["depends_on"] == [{"task_key": "land_bronze"}]
    assert tasks[2]["depends_on"] == [{"task_key": "build_silver"}]
    assert all(task["environment_key"] == "default" for task in tasks)
    assert all(task["libraries"] == [{"whl": "../../dist/*.whl"}] for task in tasks)
    assert [environment["environment_key"] for environment in job["environments"]] == ["default"]
