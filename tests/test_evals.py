"""Every trap task's grader must pass the gold answer and fail the naive answer."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

TASKS = sorted(
    p
    for p in (Path(__file__).resolve().parent.parent / "evals" / "tasks").iterdir()
    if (p / "task.json").is_file()
)


def _run_grader(task: Path, answer: dict, expected: Path, tmp_path: Path) -> dict:
    ap = tmp_path / "answer.json"
    ap.write_text(json.dumps(answer))
    out = subprocess.run(
        [sys.executable, str(task / "grade.py"), str(ap), str(expected)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


@pytest.mark.parametrize("task", TASKS, ids=[t.name for t in TASKS])
@pytest.mark.parametrize("seed", [0, 1000])
def test_grader_separates_gold_from_naive(task, seed, tmp_path):
    work, expected = tmp_path / "work", tmp_path / "expected.json"
    subprocess.run(
        [sys.executable, str(task / "generate.py"), str(work), str(expected), "--seed", str(seed)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert list((work / "data" / "raw").glob("*.csv"))
    assert (work / "docs" / "data_dictionary.md").is_file()
    exp = json.loads(expected.read_text())
    gold = _run_grader(task, exp["gold_answer"], expected, tmp_path)
    assert gold["pass"], f"gold answer failed: {gold['reasons']}"
    naive = _run_grader(task, exp["naive_answer"], expected, tmp_path)
    assert not naive["pass"], "naive (trap) answer passed the grader"
    missing = _run_grader(task, {}, expected, tmp_path)
    assert not missing["pass"]


def test_task_json_schema():
    for t in TASKS:
        meta = json.loads((t / "task.json").read_text())
        assert {"id", "failure_mode", "prompt", "answer_fields"} <= meta.keys()
        assert meta["id"] == t.name
