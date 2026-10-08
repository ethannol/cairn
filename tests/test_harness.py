"""End-to-end: init -> prereg -> freeze -> scripts -> run -> verify -> hooks."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cairn import cli, config, numbers, prereg, questions
from cairn.hooks import handlers
from cairn.verify import verify
from tests.conftest import write_prereg, write_questions

SCRIPT = """
import pandas as pd
from cairn import record, unique_key, checked_merge, censored_values, recount
wells = pd.read_csv("data/raw/wells.csv")
res = pd.read_csv("data/raw/results.csv")
unique_key(wells, "well_id")
df = checked_merge(res, wells, on="well_id", expect="m:1", how="left")
recount(res, df, "join", expect="same")
censored_values(df["result"])
record("profile.rows", len(df))
record("result.median", 1.0, unit="ug/L", n=int(df.well_id.nunique()))
record("result.unit", "ug/L")
record("result.n", int(df.well_id.nunique()))
record("result.ci_low", 0.8)
record("result.ci_high", 1.3)
"""


def _seed(root: Path) -> None:
    (root / "data/raw/wells.csv").write_text("well_id,region\nA,n\nB,s\n")
    (root / "data/raw/results.csv").write_text("well_id,result\nA,<0.5\nA,1.0\nB,1.5\nB,ND\n")
    (root / "scripts/10_analyse.py").write_text(SCRIPT)
    write_prereg(root)
    write_questions(root)


def _hook(fn, payload: dict, monkeypatch, capsys) -> dict | None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    fn()
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out.startswith("{") else None


def test_freeze_requires_complete_prereg(project):
    cfg = config.load(project)
    with pytest.raises(ValueError, match="TODO"):
        prereg.freeze(cfg)
    write_prereg(project)
    rec = prereg.freeze(cfg)
    assert "docs/prereg.md" in rec["files"]
    assert prereg.verify_frozen(cfg) == []
    (project / "docs/prereg.md").write_text((project / "docs/prereg.md").read_text() + "\nx")
    assert any("changed" in p for p in prereg.verify_frozen(cfg))


def test_full_pipeline_verify_passes_then_catches_hand_edit(project):
    _seed(project)
    cfg = config.load(project)
    prereg.freeze(cfg)
    assert cli.main(["run"]) == 0
    ledger = numbers.load_ledger(cfg.ledger_path)
    assert ledger["profile.rows"]["value"] == 4
    assert ledger["result.median"]["source"] == "10_analyse.py"
    # answer the question
    write_questions(
        project,
        [
            {
                "id": "q1",
                "text": "Did the median change?",
                "status": "answered",
                "answer_keys": ["result.median"],
                "notes": "",
            }
        ],
    )
    rep = verify(cfg, rerun=True)
    assert rep.ok, rep.summary()
    assert rep.stages["rerun"] == "pass"
    # hand-edit the ledger: the clean rerun must disagree
    ledger["result.median"]["value"] = 9.9
    cfg.ledger_path.write_text(json.dumps(ledger))
    rep = verify(cfg, rerun=True)
    assert not rep.ok and any("differs on rerun" in f for f in rep.failures)
    # render refuses missing placeholders, succeeds otherwise
    assert cli.main(["render"]) == 0
    assert "median 9.9" in (project / "report.md").read_text()


def test_verify_fails_on_unfrozen_missing_placeholder_and_failed_check(project):
    _seed(project)
    (project / "scripts/10_analyse.py").write_text(
        SCRIPT + "\nfrom cairn import unique_key\nunique_key(res, 'well_id')\n"
    )
    cfg = config.load(project)
    rep = verify(cfg, rerun=False)
    assert not rep.ok
    assert any("not been frozen" in f for f in rep.failures)
    prereg.freeze(cfg)
    cli.main(["run"])
    rep = verify(cfg, rerun=False)
    assert any("unique_key(well_id)" in f for f in rep.failures)  # results not unique by well
    (project / "report.tmpl.md").write_text("n = {{missing.key}}\n")
    rep = verify(cfg, rerun=False)
    assert any("missing.key" in f for f in rep.failures)


def test_questions_only_agent_fields_may_change(project):
    _seed(project)
    cfg = config.load(project)
    prereg.freeze(cfg)
    base = questions.load(cfg.state_dir / "questions.base.json")
    cur = json.loads(json.dumps(base))
    cur["questions"][0]["status"] = "answered"
    cur["questions"][0]["answer_keys"] = ["x"]
    assert questions.diff_problems(base, cur) == []
    cur["questions"][0]["text"] = "an easier question"
    cur["questions"].append({"id": "q9", "text": "new", "status": "open"})
    probs = questions.diff_problems(base, cur)
    assert any("'text' was changed" in p for p in probs) and any("added" in p for p in probs)
    assert (
        questions.answer_problems(cur, {})
        and "does not exist" in questions.answer_problems(cur, {})[0]
    )


def test_pre_tool_use_denies_protected_writes(project, monkeypatch, capsys):
    cfg = config.load(project)
    raw = str(cfg.root / "data/raw/x.csv")
    prereg_path = str(cfg.root / "docs/prereg.md")

    def pre(tool, ti):
        return _hook(
            handlers.pre_tool_use,
            {"cwd": str(project), "tool_name": tool, "tool_input": ti},
            monkeypatch,
            capsys,
        )

    assert pre("Write", {"file_path": raw})["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert pre("Write", {"file_path": str(cfg.root / "scripts/a.py")}) is None
    # the pre-registration is writable until frozen, read-only afterwards
    assert pre("Edit", {"file_path": prereg_path}) is None
    assert pre("Bash", {"command": "sed -i 's/a/b/' docs/prereg.md"}) is None
    write_prereg(project)
    prereg.freeze(cfg)
    assert (
        pre("Edit", {"file_path": prereg_path})["hookSpecificOutput"]["permissionDecision"]
        == "deny"
    )
    out = pre("Bash", {"command": "sed -i 's/a/b/' docs/prereg.md"})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert pre("Bash", {"command": "head data/raw/x.csv"}) is None


def test_post_tool_use_blocks_bad_script_and_unresolved_placeholder(project, monkeypatch, capsys):
    cfg = config.load(project)
    bad = cfg.root / "scripts/20_bad.py"
    bad.write_text("import pandas as pd\nout = a.merge(b, on='k')\n")
    out = _hook(
        handlers.post_tool_use,
        {"cwd": str(project), "tool_name": "Write", "tool_input": {"file_path": str(bad)}},
        monkeypatch,
        capsys,
    )
    assert out["decision"] == "block" and "C101" in out["reason"]
    tmpl = cfg.root / "report.tmpl.md"
    tmpl.write_text("The median was 2.3 and {{nope}}\n")
    out = _hook(
        handlers.post_tool_use,
        {"cwd": str(project), "tool_name": "Edit", "tool_input": {"file_path": str(tmpl)}},
        monkeypatch,
        capsys,
    )
    assert out["decision"] == "block" and "nope" in out["reason"]
    assert "bare numbers" in out["hookSpecificOutput"]["additionalContext"]


def test_stop_hook_blocks_until_verified_then_gives_up(project, monkeypatch, capsys):
    _seed(project)
    cfg = config.load(project)
    payload = {"cwd": str(project), "session_id": "s1", "stop_hook_active": False}
    out = _hook(handlers.stop, payload, monkeypatch, capsys)
    assert out["decision"] == "block" and "not been frozen" in out["reason"]
    for _ in range(cfg.stop_hook_max_blocks - 1):
        _hook(handlers.stop, payload, monkeypatch, capsys)
    out = _hook(handlers.stop, payload, monkeypatch, capsys)
    assert "decision" not in out and "stopping" in out["hookSpecificOutput"]["additionalContext"]
    # now make it pass
    (cfg.state_dir / "stop-s1.count").unlink()
    prereg.freeze(cfg)
    cli.main(["run"])
    write_questions(
        project,
        [
            {
                "id": "q1",
                "text": "Did the median change?",
                "status": "answered",
                "answer_keys": ["result.median"],
                "notes": "",
            }
        ],
    )
    out = _hook(handlers.stop, payload, monkeypatch, capsys)
    assert out is None or "decision" not in out


def test_session_start_prints_state(project, monkeypatch, capsys):
    _seed(project)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cwd": str(project)})))
    handlers.session_start()
    out = capsys.readouterr().out
    assert "NOT frozen" in out and "q1" in out


def test_cli_init_scaffolds(tmp_path):
    dest = tmp_path / "proj"
    assert cli.main(["init", str(dest)]) == 0
    assert (dest / "CLAUDE.md").is_file() and (dest / ".claude/settings.json").is_file()
    assert (dest / ".claude/skills/analysis-workflow/SKILL.md").is_file()
    assert cli.main(["init", str(dest)]) == 1  # refuses to overwrite


def test_cli_entrypoint_runs(project):
    r = subprocess.run(
        [sys.executable, "-m", "cairn.cli", "status"],
        capture_output=True,
        text=True,
        cwd=project,
        env={**os.environ, "PYTHONPATH": os.environ["PYTHONPATH"]},
    )
    assert r.returncode == 0 and "frozen:    no" in r.stdout
