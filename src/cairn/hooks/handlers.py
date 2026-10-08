from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from cairn import config, lint, numbers, questions
from cairn.config import Config

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
BASH_WRITE_HINTS = re.compile(
    r"(^|[\s;&|])(rm|mv|cp|tee|sed\s+-i|truncate|shred|dd|chmod|chown)\b|>>?|\bpython[^\n]*-c\b"
)


def _read_stdin() -> dict:
    raw = sys.stdin.read()
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


def _cfg(payload: dict) -> Config | None:
    cwd = payload.get("cwd")
    try:
        return config.load(Path(cwd) if cwd else None)
    except FileNotFoundError:
        return None


def _deny(reason: str) -> int:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


def _protected_in_command(cfg: Config, command: str) -> list[str]:
    hits: list[str] = []
    for token in re.findall(r"[\w./~-]+", command):
        p = Path(token).expanduser()
        if not p.is_absolute():
            p = cfg.root / p
        if cfg.is_protected(p):
            hits.append(token)
    return hits


# ---------------------------------------------------------------------------


def pre_tool_use() -> int:
    payload = _read_stdin()
    cfg = _cfg(payload)
    if cfg is None:
        return 0
    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input", {}) or {}
    if tool in WRITE_TOOLS:
        fp = ti.get("file_path") or ti.get("notebook_path") or ""
        if fp and cfg.is_protected(fp):
            rel = (
                Path(fp).resolve().relative_to(cfg.root.resolve()).as_posix()
                if Path(fp).is_absolute()
                else fp
            )
            return _deny(
                f"cairn: '{rel}' is a protected path (raw data, pre-registration, or harness "
                f"config). Protected patterns: {cfg.protected}. Work on derived copies under "
                f"data/derived/ or artifacts/, and record decisions in docs/decisions.md."
            )
    elif tool == "Bash":
        cmd = ti.get("command", "") or ""
        if BASH_WRITE_HINTS.search(cmd):
            hits = _protected_in_command(cfg, cmd)
            if hits:
                return _deny(
                    f"cairn: this command may modify protected paths {hits}. Protected "
                    f"patterns: {cfg.protected}. Read them freely; never write to them."
                )
    return 0


def post_tool_use() -> int:
    payload = _read_stdin()
    cfg = _cfg(payload)
    if cfg is None:
        return 0
    tool = payload.get("tool_name", "")
    if tool not in WRITE_TOOLS:
        return 0
    fp = payload.get("tool_input", {}).get("file_path") or ""
    if not fp:
        return 0
    p = Path(fp)
    notes: list[str] = []
    block: list[str] = []
    try:
        rel = p.resolve().relative_to(cfg.root.resolve())
    except ValueError:
        return 0
    if rel.suffix == ".py" and rel.parts and rel.parts[0] == cfg.scripts_dir:
        issues = lint.lint_file(p)
        for i in issues:
            (block if i.severity == "error" else notes).append(str(i))
        try:
            subprocess.run(
                [sys.executable, "-m", "py_compile", str(p)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            block.append(f"py_compile failed: {e.stderr.strip().splitlines()[-1]}")
    elif rel.as_posix() == cfg.report_template:
        ledger = numbers.load_ledger(cfg.ledger_path)
        text = p.read_text()
        _, missing = numbers.render(text, ledger)
        for k in sorted(set(missing)):
            block.append(
                f"report placeholder {{{{{k}}}}} has no ledger entry; record it with "
                f"cairn.record('{k}', ...) in a script and rerun"
            )
        bare = numbers.bare_numbers(text)
        if bare:
            notes.append(
                "bare numbers in prose (should come from the ledger via "
                "{{key}}): " + ", ".join(f"line {ln}: {lit}" for ln, lit in bare[:10])
            )
    elif rel.as_posix() == cfg.questions:
        base = cfg.state_dir / "questions.base.json"
        if base.is_file():
            probs = questions.diff_problems(questions.load(base), questions.load(p))
            block += [f"questions.json: {x}" for x in probs]
    out: dict = {}
    if block:
        out["decision"] = "block"
        out["reason"] = "cairn: " + " | ".join(block)
    if notes:
        out["hookSpecificOutput"] = {
            "hookEventName": "PostToolUse",
            "additionalContext": "cairn: " + " | ".join(notes),
        }
    if out:
        print(json.dumps(out))
    return 0


def stop() -> int:
    payload = _read_stdin()
    cfg = _cfg(payload)
    if cfg is None:
        return 0
    from cairn.verify import verify

    session = payload.get("session_id", "nosession")
    counter = cfg.state_dir / f"stop-{session}.count"
    cfg.state_dir.mkdir(exist_ok=True)
    n = int(counter.read_text()) if counter.is_file() else 0
    if n >= cfg.stop_hook_max_blocks:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "Stop",
                        "additionalContext": "cairn: verification still failing after "
                        f"{n} attempts; "
                        "stopping. Report the unresolved failures to the user.",
                    }
                }
            )
        )
        return 0
    rep = verify(cfg, rerun=cfg.stop_hook_rerun)
    if rep.ok:
        counter.unlink(missing_ok=True)
        if rep.warnings:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "Stop",
                            "additionalContext": "cairn verify passed with warnings:\n"
                            + "\n".join(rep.warnings[:10]),
                        }
                    }
                )
            )
        return 0
    counter.write_text(str(n + 1))
    reason = (
        rep.summary() + "\n\nFix these before finishing. Numbers in the report must come "
        "from cairn.record() in a script; never edit the ledger or the report by hand. "
        "If a question cannot be answered defensibly, set its status to 'abstained' with "
        "the reason in notes."
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def session_start() -> int:
    payload = _read_stdin()
    cfg = _cfg(payload)
    if cfg is None:
        return 0
    from cairn import prereg

    lines = ["cairn harness is active in this project."]
    frozen = prereg.load_frozen(cfg)
    lines.append(
        "Pre-registration: "
        + (
            f"frozen at {frozen['frozen_at']}"
            if frozen
            else "NOT frozen. Fill docs/prereg.md and run `cairn freeze` before computing results."
        )
    )
    oq = questions.open_questions(cfg)
    if oq:
        lines.append("Open questions: " + "; ".join(f"{q['id']}: {q['text'][:80]}" for q in oq))
    ledger = numbers.load_ledger(cfg.ledger_path)
    lines.append(
        f"Ledger entries: {len(ledger)}. Scripts: "
        f"{', '.join(p.name for p in sorted(cfg.scripts_path.glob('[0-9]*.py'))) or 'none'}"
    )
    v = cfg.state_dir / "verify.json"
    if v.is_file():
        last = json.loads(v.read_text())
        lines.append(
            f"Last verify: {'PASS' if last['ok'] else 'FAIL'} at {last['ran_at']}"
            + (f" ({len(last['failures'])} failures)" if not last["ok"] else "")
        )
    lines.append("Use /analysis-workflow for the required order of work.")
    print("\n".join(lines))
    return 0


HANDLERS = {
    "pre-tool-use": pre_tool_use,
    "post-tool-use": post_tool_use,
    "stop": stop,
    "session-start": session_start,
}
