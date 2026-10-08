"""`cairn verify`: the sensor the agent cannot talk its way past.

Runs, in order:
  1. frozen files unchanged (raw data, pre-registration, question list)
  2. pre-registration sections complete
  3. question list edits limited to agent-writable fields; answers cite ledger keys
  4. script lint (merge without validate, naive fills, shuffled time splits)
  5. recorded checks: no failed check in artifacts/checks.jsonl
  6. report template: every placeholder resolves; bare numbers flagged
  7. (optional) clean re-execution reproduces every ledger value
"""

from __future__ import annotations

import json
import math
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cairn import lint, numbers, pipeline, prereg, questions
from cairn.checks import read_checks
from cairn.config import Config


@dataclass
class VerifyReport:
    ok: bool = True
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stages: dict[str, str] = field(default_factory=dict)
    ran_at: str = ""

    def fail(self, stage: str, msg: str) -> None:
        self.ok = False
        self.failures.append(f"{stage}: {msg}")
        self.stages[stage] = "fail"

    def warn(self, stage: str, msg: str) -> None:
        self.warnings.append(f"{stage}: {msg}")
        self.stages.setdefault(stage, "warn")

    def passed(self, stage: str) -> None:
        self.stages.setdefault(stage, "pass")

    def summary(self, *, max_items: int = 12) -> str:
        lines = [
            f"cairn verify: {'PASS' if self.ok else 'FAIL'} "
            f"({len(self.failures)} failures, {len(self.warnings)} warnings)"
        ]
        for f in self.failures[:max_items]:
            lines.append(f"  FAIL {f}")
        if len(self.failures) > max_items:
            lines.append(f"  ... {len(self.failures) - max_items} more failures")
        for w in self.warnings[:max_items]:
            lines.append(f"  warn {w}")
        if len(self.warnings) > max_items:
            lines.append(f"  ... {len(self.warnings) - max_items} more warnings")
        return "\n".join(lines)


def _last_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[-1] if lines else ""


def _close(a: Any, b: Any, rel: float) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, int | float) and isinstance(b, int | float):
        if math.isnan(a) and math.isnan(b):
            return True
        return math.isclose(a, b, rel_tol=rel, abs_tol=rel)
    return a == b


def verify(cfg: Config, *, rerun: bool | None = None, quick: bool = False) -> VerifyReport:
    rep = VerifyReport(ran_at=datetime.now(UTC).isoformat(timespec="seconds"))
    do_rerun = cfg.verify_rerun if rerun is None else rerun
    if quick:
        do_rerun = False

    # 1. frozen files
    probs = prereg.verify_frozen(cfg)
    for p in probs:
        rep.fail("frozen", p)
    if not probs:
        rep.passed("frozen")

    # 2. prereg content
    if cfg.prereg_path.is_file():
        probs = prereg.section_problems(cfg.prereg_path.read_text())
        for p in probs:
            rep.fail("prereg", p)
        if not probs:
            rep.passed("prereg")
    else:
        rep.fail("prereg", f"{cfg.prereg} is missing")

    # 3. questions
    ledger = numbers.load_ledger(cfg.ledger_path)
    if cfg.questions_path.is_file():
        probs = questions.check(cfg, ledger)
        for p in probs:
            rep.fail("questions", p)
        n_open = len(questions.open_questions(cfg))
        if n_open:
            rep.warn("questions", f"{n_open} question(s) still open")
        if not probs:
            rep.passed("questions")

    # 4. lint
    if cfg.scripts_path.is_dir():
        issues = lint.lint_dir(cfg.scripts_path)
        for i in issues:
            (rep.fail if i.severity == "error" else rep.warn)("lint", str(i))
        if not any(i.severity == "error" for i in issues):
            rep.passed("lint")
        if not pipeline.ordered_scripts(cfg):
            rep.warn("lint", f"no NN_name.py scripts found in {cfg.scripts_dir}/")

    # 5. recorded checks
    failed = [
        c for c in read_checks(cfg.checks_path) if not c["passed"] and c.get("severity") == "error"
    ]
    for c in failed:
        rep.fail("checks", f"{c['name']} ({c.get('source')}): {c['message']}")
    warned = [
        c
        for c in read_checks(cfg.checks_path)
        if not c["passed"] and c.get("severity") == "warning"
    ]
    for c in warned:
        rep.warn("checks", f"{c['name']} ({c.get('source')}): {c['message']}")
    if not failed:
        rep.passed("checks")

    # 6. report template
    if cfg.report_template_path.is_file():
        tmpl = cfg.report_template_path.read_text()
        if not ledger:
            rep.fail("report", "ledger is empty; nothing has been recorded with cairn.record()")
        _, missing = numbers.render(tmpl, ledger)
        for k in sorted(set(missing)):
            rep.fail("report", f"placeholder {{{{{k}}}}} has no ledger entry")
        bare = numbers.bare_numbers(tmpl)
        for lineno, lit in bare[:20]:
            rep.warn("report", f"line {lineno}: bare number {lit!r} not from the ledger")
        if not numbers.placeholders(tmpl):
            rep.warn("report", "report template contains no {{placeholders}}")
        if not missing and ledger:
            rep.passed("report")
    else:
        rep.warn("report", f"{cfg.report_template} not found; nothing to render")

    # 7. clean rerun
    if do_rerun and pipeline.ordered_scripts(cfg):
        with tempfile.TemporaryDirectory(prefix="cairn-rerun-") as td:
            tmp_ledger = Path(td) / "numbers.json"
            tmp_checks = Path(td) / "checks.jsonl"
            res = pipeline.run(cfg, ledger=tmp_ledger, checks=tmp_checks)
            for s in res.steps:
                if not s.ok:
                    rep.fail(
                        "rerun",
                        f"{s.script} exited {s.returncode}: {_last_line(s.stderr_tail)}",
                    )
            if res.ok:
                fresh = numbers.load_ledger(tmp_ledger)
                for k, entry in ledger.items():
                    if k not in fresh:
                        rep.fail(
                            "rerun",
                            f"ledger key '{k}' was not produced by a clean run "
                            f"(recorded from {entry.get('source')})",
                        )
                    elif not _close(entry["value"], fresh[k]["value"], cfg.rel_tolerance):
                        rep.fail(
                            "rerun",
                            f"ledger key '{k}' differs on rerun: "
                            f"{entry['value']!r} vs {fresh[k]['value']!r}",
                        )
                for k in fresh.keys() - ledger.keys():
                    rep.warn(
                        "rerun",
                        f"clean run produced '{k}' which is not in the ledger "
                        "(run `cairn run` to refresh)",
                    )
                if "rerun" not in rep.stages:
                    rep.passed("rerun")
    elif do_rerun:
        rep.warn("rerun", "no scripts to rerun")

    cfg.state_dir.mkdir(exist_ok=True)
    (cfg.state_dir / "verify.json").write_text(json.dumps(asdict(rep), indent=2) + "\n")
    return rep
