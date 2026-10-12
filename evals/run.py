"""Run the trap suite under one or more conditions with `claude -p`.

uv run python evals/run.py --tasks all --conditions bare,cairn --trials 1 --model sonnet
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
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
        cmd.append("--safe-mode")  # no CLAUDE.md, skills, or hooks from any level; auth intact
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
    ap.add_argument("--expected-head", required=True, help="verified source commit; refuse drift")
    ap.add_argument("--fetch-time", required=True, help="UTC time of baseline remote fetch")
    ap.add_argument("--out", default=None)
    ap.add_argument("--keep", action="store_true", help="keep workdirs")
    args = ap.parse_args()

    selected = load_tasks(args.tasks)
    conditions = args.conditions.split(",")
    if not selected or any(c not in {"bare", "cairn"} for c in conditions):
        ap.error("select existing tasks and bare/cairn conditions")
    if args.trials < 1 or args.budget <= 0 or args.max_turns < 1:
        ap.error("trials, budget and max-turns must be positive")
    root = EVALS.parent
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, text=True
    )
    if head != args.expected_head or dirty.strip():
        ap.error("source revision differs from expected head or tracked files are dirty")
    import cairn

    source = Path(cairn.__file__).resolve()
    if not source.is_relative_to(root):
        ap.error(f"runtime cairn is not from this verified checkout: {source}")
    cli_version = subprocess.check_output(["claude", "--version"], text=True).strip()
    cli_help = subprocess.check_output(["claude", "--help"], text=True)
    for flag in ["--safe-mode", "--setting-sources", "--max-budget-usd", "--max-turns"]:
        if flag not in cli_help:
            ap.error(f"installed Claude CLI lacks required flag {flag}")
    tracked = subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines()
    hashes = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in tracked
        if (root / name).is_file()
    }
    manifest = {
        "fetch_time_utc": args.fetch_time,
        "git_head": head,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "instrumentation_patch": None,
        "source_sha256": hashes,
        "runtime": {
            "python": PY,
            "version": platform.python_version(),
            "cairn_source": str(source),
            "packages": {
                name: importlib.metadata.version(name)
                for name in ["cairn", "pandas", "numpy", "scipy", "scikit-learn"]
            },
        },
        "claude_version": cli_version,
        "claude_help_sha256": hashlib.sha256(cli_help.encode()).hexdigest(),
        "configuration": vars(args),
        "seeds": [1000 + n for n in range(args.trials)],
        "tool_configuration": "bare: safe-mode; cairn: project settings and bundled template",
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else EVALS / "runs" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows: list[dict] = []
    for task_dir in selected:
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
                (trial_dir / "prompt.txt").write_text(prompt)
                shutil.copy2(expected, trial_dir / "expected.json")
                raw_hashes = {
                    str(p.relative_to(workdir)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted((workdir / "data/raw").rglob("*"))
                    if p.is_file()
                }
                (trial_dir / "config.json").write_text(
                    json.dumps(
                        {
                            "task": task_dir.name,
                            "condition": condition,
                            "seed": seed,
                            "source_head": head,
                            "model_requested": args.model,
                            "raw_sha256": raw_hashes,
                        },
                        indent=2,
                    )
                    + "\n"
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
