"""Shared helpers for eval task generators and graders."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=_jsonable) + "\n")


def _jsonable(x: Any) -> Any:
    try:
        import numpy as np

        if isinstance(x, np.generic):
            return x.item()
        if isinstance(x, np.ndarray):
            return x.tolist()
    except ImportError:  # pragma: no cover
        pass
    return str(x)


def close(a: Any, b: Any, *, rel: float = 0.0, abs_: float = 0.0) -> bool:
    try:
        return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_)
    except (TypeError, ValueError):
        return False


class Grade:
    def __init__(self) -> None:
        self.reasons: list[str] = []
        self.details: dict[str, Any] = {}

    def require(self, ok: bool, reason: str) -> bool:
        if not ok:
            self.reasons.append(reason)
        return ok

    def result(self) -> dict[str, Any]:
        return {"pass": not self.reasons, "reasons": self.reasons, "details": self.details}


def grader_main(fn) -> None:
    """`python grade.py answer.json expected.json` -> prints a JSON verdict."""
    answer_path, expected_path = Path(sys.argv[1]), Path(sys.argv[2])
    expected = json.loads(expected_path.read_text())
    if not answer_path.is_file():
        print(json.dumps({"pass": False, "reasons": ["answer.json not written"], "details": {}}))
        return
    try:
        answer = json.loads(answer_path.read_text())
    except json.JSONDecodeError as e:
        print(json.dumps({"pass": False, "reasons": [f"answer.json invalid: {e}"], "details": {}}))
        return
    print(json.dumps(fn(answer, expected), default=_jsonable))


def generator_main(fn) -> None:
    """`python generate.py <workdir> <expected.json> [--seed N]`."""
    workdir, expected_path = Path(sys.argv[1]), Path(sys.argv[2])
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 0
    (workdir / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (workdir / "docs").mkdir(parents=True, exist_ok=True)
    expected = fn(workdir, seed)
    write_json(expected_path, expected)
