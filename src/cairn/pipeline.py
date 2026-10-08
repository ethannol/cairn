"""Run the analysis scripts in order, from a clean state, and write a manifest."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cairn.checks import file_sha256
from cairn.config import Config


@dataclass
class StepResult:
    script: str
    returncode: int
    seconds: float
    stdout_tail: str
    stderr_tail: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class RunResult:
    started_at: str
    steps: list[StepResult] = field(default_factory=list)
    inputs: dict[str, str] = field(default_factory=dict)
    git_head: str | None = None
    ledger_path: str = ""

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps)


def ordered_scripts(cfg: Config) -> list[Path]:
    """Scripts named NN_name.py run in numeric order; others are ignored."""
    return sorted(p for p in cfg.scripts_path.glob("[0-9][0-9]*_*.py") if p.is_file())


def _tail(s: str, n: int = 2000) -> str:
    return s if len(s) <= n else "..." + s[-n:]


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


def run(
    cfg: Config,
    *,
    ledger: Path | None = None,
    checks: Path | None = None,
    timeout: int | None = None,
    echo: bool = False,
) -> RunResult:
    """Execute every ordered script with `cfg.runner`, writing the ledger to `ledger`.

    A rerun for verification passes a separate ledger path so the committed
    ledger is never touched by the check that validates it.
    """
    res = RunResult(
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        git_head=_git_head(cfg.root),
        ledger_path=str(ledger or cfg.ledger_path),
    )
    raw = cfg.root / "data" / "raw"
    if raw.is_dir():
        for p in sorted(raw.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                res.inputs[p.relative_to(cfg.root).as_posix()] = file_sha256(p)
    env = dict(os.environ)
    env["CAIRN_LEDGER"] = str(ledger or cfg.ledger_path)
    env["CAIRN_CHECKS"] = str(checks or cfg.checks_path)
    env["CAIRN_RERUN"] = "1" if ledger else "0"
    env["PYTHONHASHSEED"] = "0"
    for lp in (ledger, checks):
        if lp is not None and lp.exists():
            lp.unlink()
    runner = shlex.split(cfg.runner)
    for script in ordered_scripts(cfg):
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                [*runner, str(script)],
                cwd=cfg.root,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout or cfg.rerun_timeout,
            )
            rc, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            rc, out, err = (
                124,
                (e.stdout or b"").decode(errors="replace")
                if isinstance(e.stdout, bytes)
                else (e.stdout or ""),
                f"timeout after {timeout or cfg.rerun_timeout}s",
            )
        step = StepResult(
            script.relative_to(cfg.root).as_posix(),
            rc,
            round(time.monotonic() - t0, 2),
            _tail(out),
            _tail(err),
        )
        res.steps.append(step)
        if echo:
            print(f"[{'ok' if step.ok else 'FAIL'}] {step.script} ({step.seconds}s)")
            if not step.ok:
                print(step.stderr_tail)
        if not step.ok:
            break
    runs_dir = cfg.state_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{res.started_at.replace(':', '')}.json").write_text(
        json.dumps(asdict(res), indent=2) + "\n"
    )
    return res
