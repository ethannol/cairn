"""Run the trap suite under one or more conditions with `claude -p`.

uv run python evals/run.py --tasks all --conditions bare,cairn --trials 1 --model sonnet
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

EVALS = Path(__file__).resolve().parent
TASKS = EVALS / "tasks"
PY = sys.executable
VENV_BIN = Path(PY).parent

COMMON_PROMPT = """You are working in {workdir}. The data are in data/raw/ and are documented in
docs/data_dictionary.md. Use Python (pandas, numpy, scipy and scikit-learn are installed).

Task: {task}

Write your final answer as JSON to {workdir}/answer.json with exactly these fields:
{fields}

Compute every number with code you ran. Do not stop until answer.json exists.
"""


def load_tasks(selection: str) -> list[Path]:
    all_tasks = sorted(p for p in TASKS.iterdir() if (p / "task.json").is_file())
    if selection == "all":
        return all_tasks
    wanted = set(selection.split(","))
    return [p for p in all_tasks if p.name in wanted or p.name.split("_")[0] in wanted]


def prepare_workdir(task_dir: Path, condition: str, seed: int, base: Path) -> tuple[Path, Path]:
    workdir = base / "work"
    expected = base / "expected.json"
    workdir.mkdir(parents=True)
    subprocess.run(
        [PY, str(task_dir / "generate.py"), str(workdir), str(expected), "--seed", str(seed)],
        check=True,
        capture_output=True,
        text=True,
    )
    if condition == "cairn":
        subprocess.run(
            [str(VENV_BIN / "cairn"), "init", str(workdir)],
            check=True,
            capture_output=True,
            text=True,
        )
        toml = workdir / "cairn.toml"
        toml.write_text(
            toml.read_text().replace('runner = "uv run --locked python"', f'runner = "{PY}"')
        )
        subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
        subprocess.run(["git", "add", "-A"], cwd=workdir, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=cairn",
                "-c",
                "user.email=cairn@example.com",
                "commit",
                "-qm",
                "init",
            ],
            cwd=workdir,
            check=True,
        )
    return workdir, expected


def run_claude(
    workdir: Path,
    prompt: str,
    condition: str,
    model: str,
    max_turns: int,
    budget: float,
    timeout: int,
) -> dict:
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--model",
        model,
        "--max-turns",
        str(max_turns),
        "--max-budget-usd",
        f"{budget:.2f}",
        "--dangerously-skip-permissions",
        "--no-session-persistence",
    ]
    if condition == "bare":
        cmd.append("--bare")
    else:
        cmd += ["--setting-sources", "project"]
    env = dict(os.environ)
    env["PATH"] = f"{VENV_BIN}:{env.get('PATH', '')}"
    env["VIRTUAL_ENV"] = str(VENV_BIN.parent)
    env.pop("CLAUDE_PROJECT_DIR", None)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=workdir, env=env, capture_output=True, text=True, timeout=timeout
        )
        raw, err, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        raw, err, rc = (e.stdout or ""), f"timeout after {timeout}s", 124
    wall = round(time.monotonic() - t0, 1)
    try:
        out = json.loads(raw) if raw.strip().startswith("{") else {"result": raw}
    except json.JSONDecodeError:
        out = {"result": raw}
    out["_rc"], out["_stderr_tail"], out["_wall_s"] = rc, err[-2000:], wall
    return out


def grade(task_dir: Path, workdir: Path, expected: Path) -> dict:
    proc = subprocess.run(
        [PY, str(task_dir / "grade.py"), str(workdir / "answer.json"), str(expected)],
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"pass": False, "reasons": [f"grader crashed: {proc.stderr[-500:]}"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--conditions", default="bare,cairn")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--max-turns", type=int, default=80)
    ap.add_argument("--budget", type=float, default=3.0, help="USD cap per trial")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds per trial")
    ap.add_argument("--out", default=None)
    ap.add_argument("--keep", action="store_true", help="keep workdirs")
    args = ap.parse_args()

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else EVALS / "runs" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for task_dir in load_tasks(args.tasks):
        task = json.loads((task_dir / "task.json").read_text())
        for condition in args.conditions.split(","):
            for trial in range(args.trials):
                seed = 1000 + trial
                trial_dir = out_dir / task_dir.name / condition / f"trial{trial}"
                trial_dir.mkdir(parents=True, exist_ok=True)
                base = Path(tempfile.mkdtemp(prefix=f"cairn-eval-{task_dir.name}-"))
                workdir, expected = prepare_workdir(task_dir, condition, seed, base)
                prompt = COMMON_PROMPT.format(
                    workdir=workdir,
                    task=task["prompt"],
                    fields=json.dumps(task["answer_fields"], indent=2),
                )
                print(f"[{task_dir.name} | {condition} | trial {trial}] running...", flush=True)
                res = run_claude(
                    workdir,
                    prompt,
                    condition,
                    args.model,
                    args.max_turns,
                    args.budget,
                    args.timeout,
                )
                verdict = grade(task_dir, workdir, expected)
                (trial_dir / "claude.json").write_text(json.dumps(res, indent=2))
                (trial_dir / "grade.json").write_text(json.dumps(verdict, indent=2))
                for name in (
                    "answer.json",
                    "report.tmpl.md",
                    "docs/prereg.md",
                    "artifacts/numbers.json",
                    "artifacts/checks.jsonl",
                ):
                    src = workdir / name
                    if src.is_file():
                        dst = trial_dir / name.replace("/", "__")
                        shutil.copy2(src, dst)
                if (workdir / "scripts").is_dir():
                    shutil.copytree(workdir / "scripts", trial_dir / "scripts", dirs_exist_ok=True)
                row = {
                    "task": task_dir.name,
                    "failure_mode": task["failure_mode"],
                    "condition": condition,
                    "trial": trial,
                    "pass": verdict["pass"],
                    "reasons": verdict.get("reasons", []),
                    "cost_usd": res.get("total_cost_usd"),
                    "turns": res.get("num_turns"),
                    "wall_s": res.get("_wall_s"),
                    "rc": res.get("_rc"),
                    "is_error": res.get("is_error"),
                }
                rows.append(row)
                print(
                    f"    -> {'PASS' if row['pass'] else 'FAIL'} "
                    f"cost=${row['cost_usd'] or 0:.2f} turns={row['turns']} "
                    f"{'; '.join(row['reasons'][:2])}",
                    flush=True,
                )
                if not args.keep:
                    shutil.rmtree(base, ignore_errors=True)
                else:
                    (trial_dir / "WORKDIR").write_text(str(workdir))
    (out_dir / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (out_dir / "summary.md").write_text(summarise(rows, args))
    print((out_dir / "summary.md").read_text())
    return 0


def summarise(rows: list[dict], args: argparse.Namespace) -> str:
    conds = args.conditions.split(",")
    lines = [
        f"# Trap suite results ({args.model}, {args.trials} trial(s), "
        f"max {args.max_turns} turns, ${args.budget:.2f} cap)",
        "",
        "| task | failure mode | "
        + " | ".join(f"{c} pass" for c in conds)
        + " | "
        + " | ".join(f"{c} $/trial" for c in conds)
        + " |",
        "|---|---|" + "---|" * (2 * len(conds)),
    ]
    tasks = sorted({r["task"] for r in rows})
    for t in tasks:
        cells, costs = [], []
        fm = next(r["failure_mode"] for r in rows if r["task"] == t)
        for c in conds:
            rs = [r for r in rows if r["task"] == t and r["condition"] == c]
            cells.append(f"{sum(r['pass'] for r in rs)}/{len(rs)}" if rs else "-")
            cs = [r["cost_usd"] for r in rs if r["cost_usd"] is not None]
            costs.append(f"{sum(cs) / len(cs):.2f}" if cs else "-")
        lines.append(f"| {t} | {fm} | " + " | ".join(cells) + " | " + " | ".join(costs) + " |")
    for c in conds:
        rs = [r for r in rows if r["condition"] == c]
        if rs:
            lines.append(
                f"\n**{c}**: {sum(r['pass'] for r in rs)}/{len(rs)} passed; total "
                f"estimated cost ${sum(r['cost_usd'] or 0 for r in rs):.2f}"
            )
    lines.append("\nCosts are the CLI's client-side estimates. Raw outputs are beside this file.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
