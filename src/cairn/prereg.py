"""Pre-registration: freeze the analysis plan before computing.

`cairn freeze` hashes docs/prereg.md and the question list into
`.cairn/frozen.json`. From then on the pre-registration is a protected path
and `cairn verify` fails if its hash changes. Exploratory work is allowed, but
it has to be labelled as such in the report.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from cairn.checks import file_sha256
from cairn.config import Config

REQUIRED_SECTIONS = [
    "Question",
    "Primary quantity",
    "Unit of analysis",
    "Population and comparability",
    "Handling of missing and censored values",
    "Decision rule",
    "Confirmatory vs exploratory",
]
PLACEHOLDER_WORDS = re.compile(r"\b(TODO|TBD|FILL ?ME|XXX)\b", re.I)


def frozen_path(cfg: Config) -> Path:
    return cfg.state_dir / "frozen.json"


def load_frozen(cfg: Config) -> dict | None:
    p = frozen_path(cfg)
    return json.loads(p.read_text()) if p.is_file() else None


def section_problems(text: str) -> list[str]:
    """Required headings present and filled in (no TODO, at least one sentence)."""
    problems: list[str] = []
    for sec in REQUIRED_SECTIONS:
        m = re.search(rf"^#+\s*{re.escape(sec)}\s*$(.*?)(?=^#+\s|\Z)", text, re.M | re.S | re.I)
        if not m:
            problems.append(f"missing section '{sec}'")
            continue
        body = m.group(1).strip()
        if len(body) < 20:
            problems.append(f"section '{sec}' is empty or too short")
        elif PLACEHOLDER_WORDS.search(body):
            problems.append(f"section '{sec}' still contains a placeholder (TODO/TBD)")
    return problems


def _git_head(root: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def freeze(cfg: Config, *, allow_incomplete: bool = False) -> dict:
    text = cfg.prereg_path.read_text()
    problems = section_problems(text)
    if problems and not allow_incomplete:
        raise ValueError("pre-registration is incomplete:\n  - " + "\n  - ".join(problems))
    record = {
        "frozen_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_head": _git_head(cfg.root),
        "files": {},
    }
    # questions.json is snapshotted, not hashed: the agent may change its
    # status/answer fields and questions.diff_problems polices the rest.
    record["files"][cfg.prereg] = file_sha256(cfg.prereg_path)
    raw_dir = cfg.root / "data" / "raw"
    if raw_dir.is_dir():
        for p in sorted(raw_dir.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                record["files"][p.relative_to(cfg.root).as_posix()] = file_sha256(p)
    cfg.state_dir.mkdir(exist_ok=True)
    frozen_path(cfg).write_text(json.dumps(record, indent=2) + "\n")
    # Snapshot the question list so later edits can be diffed.
    if cfg.questions_path.is_file():
        (cfg.state_dir / "questions.base.json").write_text(cfg.questions_path.read_text())
    return record


def verify_frozen(cfg: Config) -> list[str]:
    """Return a list of problems: unfrozen, changed, or missing protected files."""
    rec = load_frozen(cfg)
    if rec is None:
        return ["pre-registration has not been frozen (run `cairn freeze`)"]
    problems = []
    for rel, digest in rec["files"].items():
        p = cfg.root / rel
        if not p.is_file():
            problems.append(f"frozen file missing: {rel}")
        elif file_sha256(p) != digest:
            problems.append(f"frozen file changed since freeze: {rel}")
    return problems
