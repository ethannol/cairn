"""The numbers ledger.

Every figure that appears in a report must be produced by code and recorded
here with its provenance. Report templates reference ledger keys with
`{{key}}` or `{{key:.2f}}`; `cairn render` substitutes them and `cairn verify`
refuses a report with unresolved keys, and re-derives the ledger from a clean
run to catch numbers that were edited by hand.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LEDGER_ENV = "CAIRN_LEDGER"
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*(?::([^}]+))?\s*\}\}")


def _default_ledger_path() -> Path:
    env = os.environ.get(LEDGER_ENV)
    if env:
        return Path(env)
    from cairn.config import find_root

    root = find_root()
    base = root if root is not None else Path.cwd()
    return base / "artifacts" / "numbers.json"


def _caller_source() -> str:
    main = sys.modules.get("__main__")
    f = getattr(main, "__file__", None)
    if f:
        return Path(f).name
    return "<interactive>"


def load_ledger(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p = path or _default_ledger_path()
    if not p.is_file():
        return {}
    return json.loads(p.read_text())


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".numbers-", suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True, default=_jsonable)
        fh.write("\n")
    os.replace(tmp, path)


def _jsonable(x: Any) -> Any:
    try:
        import numpy as np

        if isinstance(x, np.generic):
            return x.item()
    except ImportError:  # pragma: no cover
        pass
    if hasattr(x, "isoformat"):
        return x.isoformat()
    return str(x)


def record(
    key: str,
    value: Any,
    *,
    unit: str | None = None,
    n: int | None = None,
    note: str | None = None,
    source: str | None = None,
    ledger: Path | None = None,
) -> Any:
    """Record `value` under `key` with provenance. Returns `value` for chaining.

    Keys are dotted identifiers, e.g. ``record("arsenic.median_ugL", 2.1, n=412)``.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", key):
        raise ValueError(f"ledger key must be a dotted identifier, got {key!r}")
    path = ledger or _default_ledger_path()
    data = load_ledger(path)
    entry: dict[str, Any] = {
        "value": _jsonable(value) if not isinstance(value, int | float | str | bool) else value,
        "source": source or _caller_source(),
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if unit is not None:
        entry["unit"] = unit
    if n is not None:
        entry["n"] = int(n)
    if note is not None:
        entry["note"] = note
    data[key] = entry
    _write_atomic(path, data)
    return value


def _format(value: Any, spec: str | None) -> str:
    if spec:
        try:
            return format(value, spec)
        except (ValueError, TypeError):
            return str(value)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def render(template: str, ledger: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    """Substitute `{{key}}` placeholders. Returns (text, missing_keys)."""
    missing: list[str] = []

    def sub(m: re.Match) -> str:
        key, spec = m.group(1), m.group(2)
        if key not in ledger:
            missing.append(key)
            return m.group(0)
        return _format(ledger[key]["value"], spec)

    return PLACEHOLDER.sub(sub, template), missing


def placeholders(template: str) -> list[str]:
    return [m.group(1) for m in PLACEHOLDER.finditer(template)]


_CODE_BLOCK = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`]*`")
_NUMBER = re.compile(r"(?<![\w.{/-])[-+]?\d[\d,]*(?:\.\d+)?%?(?![\w}])")


def bare_numbers(template: str, *, allow_years: bool = True) -> list[tuple[int, str]]:
    """Numeric literals written directly into prose (not via a placeholder).

    Heuristic. Ignores code blocks, inline code, list/heading markers, and
    4-digit years between 1900 and 2100 when `allow_years`. Returns
    (line_number, literal) pairs for a human or a hook to review.
    """
    text = _CODE_BLOCK.sub(lambda m: "\n" * m.group(0).count("\n"), template)
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = _INLINE_CODE.sub("", line)
        stripped = PLACEHOLDER.sub("", stripped)
        stripped = re.sub(r"^\s*(#+|\d+[.)]|[-*+])\s+", "", stripped)
        stripped = re.sub(r"\[[^\]]*\]\([^)]*\)", "", stripped)
        for m in _NUMBER.finditer(stripped):
            lit = m.group(0)
            digits = lit.replace(",", "").rstrip("%").lstrip("+-")
            if allow_years and re.fullmatch(r"(19|20)\d{2}", digits):
                continue
            if re.fullmatch(r"[01]", digits):
                continue
            found.append((lineno, lit))
    return found
