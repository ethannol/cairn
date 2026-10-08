"""`cairn` command line."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from cairn import __version__, config, numbers, pipeline, prereg, profile, questions
from cairn.config import CONFIG_NAME, Config

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "template"


def _cfg(args: argparse.Namespace) -> Config:
    return config.load(Path(args.root) if getattr(args, "root", None) else None)


def cmd_init(args: argparse.Namespace) -> int:
    dest = Path(args.dir or ".").resolve()
    dest.mkdir(parents=True, exist_ok=True)
    if (dest / CONFIG_NAME).exists() and not args.force:
        print(f"{dest / CONFIG_NAME} already exists (use --force to overwrite template files)")
        return 1
    copied = 0
    for src in TEMPLATE_DIR.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(TEMPLATE_DIR)
        target = dest / rel
        if target.exists() and not args.force:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied += 1
    for d in ("data/raw", "data/derived", "artifacts", "profiles", "scripts", ".cairn"):
        (dest / d).mkdir(parents=True, exist_ok=True)
    print(
        f"cairn: initialised {dest} ({copied} template files). Next: put raw data in "
        f"data/raw/, run `cairn profile data/raw/*`, fill docs/prereg.md and questions.json, "
        f"then `cairn freeze`."
    )
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    paths = [Path(p) for p in args.files]
    written = profile.profile_files(paths, cfg.root / cfg.profiles_dir)
    for w in written:
        if w.suffix == ".md":
            print(w.read_text())
    print(f"cairn: wrote {len(written)} profile files to {cfg.profiles_dir}/")
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    try:
        rec = prereg.freeze(cfg, allow_incomplete=args.allow_incomplete)
    except ValueError as e:
        print(f"cairn: {e}")
        return 1
    print(
        f"cairn: froze {len(rec['files'])} files at {rec['frozen_at']} "
        f"(git {rec['git_head'] or 'n/a'}). Commit .cairn/frozen.json."
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    res = pipeline.run(cfg, echo=True, timeout=args.timeout)
    print(
        f"cairn: {'all steps ok' if res.ok else 'a step failed'}; "
        f"ledger has {len(numbers.load_ledger(cfg.ledger_path))} entries"
    )
    return 0 if res.ok else 1


def cmd_verify(args: argparse.Namespace) -> int:
    from cairn.verify import verify

    cfg = _cfg(args)
    rerun = None if args.rerun is None else args.rerun
    rep = verify(cfg, rerun=rerun, quick=args.quick)
    print(rep.summary(max_items=50))
    return 0 if rep.ok else 1


def cmd_render(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    tmpl = cfg.report_template_path.read_text()
    text, missing = numbers.render(tmpl, numbers.load_ledger(cfg.ledger_path))
    if missing:
        print("cairn: unresolved placeholders: " + ", ".join(sorted(set(missing))))
        return 1
    cfg.report_path.write_text(text)
    print(f"cairn: rendered {cfg.report} from {cfg.report_template}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    frozen = prereg.load_frozen(cfg)
    ledger = numbers.load_ledger(cfg.ledger_path)
    qs = questions.load(cfg.questions_path).get("questions", [])
    print(f"project:   {cfg.root}")
    print(f"frozen:    {frozen['frozen_at'] if frozen else 'no'}")
    print(f"scripts:   {[p.name for p in pipeline.ordered_scripts(cfg)]}")
    print(f"ledger:    {len(ledger)} entries")
    by_status: dict[str, int] = {}
    for q in qs:
        by_status[q.get("status", "open")] = by_status.get(q.get("status", "open"), 0) + 1
    print(f"questions: {by_status or 'none'}")
    if args.json:
        print(
            json.dumps(
                {"root": str(cfg.root), "frozen": frozen, "ledger": ledger, "questions": qs},
                indent=2,
            )
        )
    return 0


def cmd_ledger(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    ledger = numbers.load_ledger(cfg.ledger_path)
    for k, v in sorted(ledger.items()):
        extra = " ".join(f"{f}={v[f]}" for f in ("unit", "n") if f in v)
        print(f"{k:40s} {v['value']!r:>20}  {extra}  <- {v.get('source')}")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    from cairn.hooks.handlers import HANDLERS

    return HANDLERS[args.event]()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cairn", description=__doc__)
    p.add_argument("--version", action="version", version=f"cairn {__version__}")
    p.add_argument("--root", help="project root (default: nearest cairn.toml)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="scaffold a project with CLAUDE.md, skills, hooks, cairn.toml")
    s.add_argument("dir", nargs="?")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("profile", help="profile raw tables into profiles/")
    s.add_argument("files", nargs="+")
    s.set_defaults(fn=cmd_profile)

    s = sub.add_parser("freeze", help="freeze pre-registration, question list and raw data")
    s.add_argument("--allow-incomplete", action="store_true")
    s.set_defaults(fn=cmd_freeze)

    s = sub.add_parser("run", help="run scripts/NN_*.py in order, rebuilding the ledger")
    s.add_argument("--timeout", type=int)
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("verify", help="run all sensors; exit 1 on any failure")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--rerun", dest="rerun", action="store_true", default=None)
    g.add_argument("--no-rerun", dest="rerun", action="store_false")
    s.add_argument("--quick", action="store_true", help="skip the clean re-execution")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("render", help="substitute ledger values into the report template")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("status", help="show freeze, scripts, ledger and question state")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("ledger", help="list recorded numbers with provenance")
    s.set_defaults(fn=cmd_ledger)

    s = sub.add_parser("hook", help="Claude Code hook entrypoint (reads JSON on stdin)")
    s.add_argument("event", choices=["pre-tool-use", "post-tool-use", "stop", "session-start"])
    s.set_defaults(fn=cmd_hook)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except FileNotFoundError as e:
        print(f"cairn: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
