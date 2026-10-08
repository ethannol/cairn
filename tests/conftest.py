import json
import os
import shutil
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parent.parent / "template"


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A fresh cairn project in tmp_path, cwd set there, env isolated."""
    for src in TEMPLATE.rglob("*"):
        if src.is_file():
            dest = tmp_path / src.relative_to(TEMPLATE)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    for d in ("data/raw", "data/derived", "artifacts", "profiles", "scripts", ".cairn"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    # Tests run scripts with the current interpreter, not uv.
    toml = tmp_path / "cairn.toml"
    toml.write_text(
        toml.read_text().replace(
            'runner = "uv run --locked python"', f'runner = "{os.sys.executable}"'
        )
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CAIRN_LEDGER", raising=False)
    monkeypatch.delenv("CAIRN_CHECKS", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parent.parent / "src"))
    return tmp_path


def write_prereg(root: Path) -> None:
    (root / "docs" / "prereg.md").write_text("""# Pre-registration

## Question
Did the median arsenic concentration at repeatedly sampled wells change between periods?

## Primary quantity
Difference in per-well median arsenic (ug/L) between the two periods, consistent cohort.

## Unit of analysis
The well. Repeated samples within a well are summarised to one value per period.

## Population and comparability
Field samples only; QC rows excluded; dissolved fraction only; ug/L after conversion.

## Handling of missing and censored values
Non-detects handled by interval bounds; substitution only as a labelled sensitivity check.

## Decision rule
Report a change only if the unit-level bootstrap interval excludes zero; else no change.

## Confirmatory vs exploratory
Only the above is confirmatory. Everything else will be labelled exploratory.
""")


def write_questions(root: Path, qs=None) -> None:
    qs = qs or [
        {
            "id": "q1",
            "text": "Did the median change?",
            "status": "open",
            "answer_keys": [],
            "notes": "",
        }
    ]
    (root / "questions.json").write_text(json.dumps({"questions": qs}, indent=2))
