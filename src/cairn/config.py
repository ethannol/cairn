"""Project configuration: `cairn.toml` at the project root."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = "cairn.toml"
STATE_DIR = ".cairn"


@dataclass
class Config:
    root: Path
    protected: list[str] = field(
        default_factory=lambda: ["data/raw/**", "cairn.toml", ".claude/**", ".cairn/frozen.json"]
    )
    scripts_dir: str = "scripts"
    artifacts_dir: str = "artifacts"
    profiles_dir: str = "profiles"
    report_template: str = "report.tmpl.md"
    report: str = "report.md"
    prereg: str = "docs/prereg.md"
    questions: str = "questions.json"
    runner: str = "uv run --locked python"
    verify_rerun: bool = True
    rerun_timeout: int = 900
    rel_tolerance: float = 1e-6
    stop_hook_max_blocks: int = 3
    stop_hook_rerun: bool = False

    # Derived paths -------------------------------------------------------
    @property
    def state_dir(self) -> Path:
        return self.root / STATE_DIR

    @property
    def ledger_path(self) -> Path:
        return self.root / self.artifacts_dir / "numbers.json"

    @property
    def checks_path(self) -> Path:
        return self.root / self.artifacts_dir / "checks.jsonl"

    @property
    def prereg_path(self) -> Path:
        return self.root / self.prereg

    @property
    def questions_path(self) -> Path:
        return self.root / self.questions

    @property
    def report_template_path(self) -> Path:
        return self.root / self.report_template

    @property
    def report_path(self) -> Path:
        return self.root / self.report

    @property
    def scripts_path(self) -> Path:
        return self.root / self.scripts_dir

    def frozen_files(self) -> set[str]:
        """Root-relative paths hashed by `cairn freeze` (protected once frozen)."""
        p = self.state_dir / "frozen.json"
        if not p.is_file():
            return set()
        try:
            return set(json.loads(p.read_text()).get("files", {}))
        except (json.JSONDecodeError, AttributeError):
            return set()

    def is_protected(self, path: Path | str) -> bool:
        """True if `path` matches a protected pattern or was frozen by `cairn freeze`.

        The pre-registration is deliberately writable before the freeze and
        read-only after it; raw data and harness config are always read-only.
        """
        p = Path(path)
        if p.is_absolute():
            try:
                p = p.resolve().relative_to(self.root.resolve())
            except ValueError:
                return False
        rel = p.as_posix()
        for pattern in self.protected:
            if _glob_match(rel, pattern):
                return True
        return rel in self.frozen_files()


def _glob_match(rel: str, pattern: str) -> bool:
    """Match a root-relative posix path against a pattern with `**` support."""
    if pattern.endswith("/**"):
        base = pattern[:-3]
        return rel == base or rel.startswith(base + "/")
    if "**" in pattern:
        return Path(rel).match(pattern)
    return rel == pattern or Path(rel).match(pattern)


def find_root(start: Path | None = None) -> Path | None:
    """Walk up from `start` (or $CLAUDE_PROJECT_DIR, or cwd) to find cairn.toml."""
    candidates = []
    if start is not None:
        candidates.append(Path(start))
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        candidates.append(Path(env_root))
    candidates.append(Path.cwd())
    for c in candidates:
        for d in [c, *c.parents]:
            if (d / CONFIG_NAME).is_file():
                return d
    return None


def load(root: Path | None = None) -> Config:
    """Load `cairn.toml` from `root` or the nearest ancestor of cwd."""
    found = root if root is not None and (root / CONFIG_NAME).is_file() else find_root(root)
    if found is None:
        raise FileNotFoundError(
            f"No {CONFIG_NAME} found. Run `cairn init` in the project directory first."
        )
    data = tomllib.loads((found / CONFIG_NAME).read_text())
    cfg = Config(root=found.resolve())
    for key, value in data.items():
        if hasattr(cfg, key) and key != "root":
            setattr(cfg, key, value)
    return cfg
