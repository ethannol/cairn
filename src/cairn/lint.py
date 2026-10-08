"""Static checks on analysis scripts.

Deterministic, cheap, and narrow on purpose: these catch the shapes of code
that produce clean-running wrong numbers. They do not try to judge semantics.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LintIssue:
    path: Path
    line: int
    code: str
    message: str
    severity: str = "error"

    def __str__(self) -> str:
        return f"{self.path.name}:{self.line}: {self.code} {self.message}"


MERGE_NAMES = {"merge", "join"}
NAIVE_FILL = {"fillna"}


def lint_source(src: str, path: Path) -> list[LintIssue]:
    issues: list[LintIssue] = []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return [LintIssue(path, e.lineno or 0, "C000", f"syntax error: {e.msg}")]

    uses_checked_merge = "checked_merge" in src
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else (func.id if isinstance(func, ast.Name) else None)
        )
        kw = {k.arg for k in node.keywords}
        if name == "merge" and "validate" not in kw:
            is_pd_merge = (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "pd"
            )
            # `df.merge(other, ...)` or `pd.merge(a, b, ...)` without validate=
            if is_pd_merge or isinstance(func, ast.Attribute):
                issues.append(
                    LintIssue(
                        path,
                        node.lineno,
                        "C101",
                        "merge without validate= ; use cairn.checked_merge(...) or pass "
                        "validate='many_to_one' etc. after a join_check",
                    )
                )
        if (
            name == "join"
            and isinstance(func, ast.Attribute)
            and "validate" not in kw
            and not uses_checked_merge
        ):
            issues.append(
                LintIssue(
                    path,
                    node.lineno,
                    "C102",
                    "DataFrame.join without validate=; check cardinality first",
                    severity="warning",
                )
            )
        if (
            name == "fillna"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == 0
        ):
            issues.append(
                LintIssue(
                    path,
                    node.lineno,
                    "C201",
                    "fillna(0): a missing value is not a zero; justify in a comment or use "
                    "an explicit indicator",
                    severity="warning",
                )
            )
        if name == "train_test_split" and "shuffle" not in kw and "stratify" not in kw:
            issues.append(
                LintIssue(
                    path,
                    node.lineno,
                    "C301",
                    "train_test_split with default shuffle: if rows have a time order this "
                    "leaks the future; use a time-based split and run cairn.time_leak",
                    severity="warning",
                )
            )
        if name in {"fit_transform", "fit"} and isinstance(func, ast.Attribute):
            # fit on something named like the full data
            arg0 = node.args[0] if node.args else None
            if isinstance(arg0, ast.Name) and arg0.id in {"X", "df", "data", "features"}:
                issues.append(
                    LintIssue(
                        path,
                        node.lineno,
                        "C302",
                        f"{name}({arg0.id}): fitting on a frame named like the full dataset; "
                        "preprocessing must be fit on train only",
                        severity="warning",
                    )
                )
    # Hard-coded result numbers in print statements that look like conclusions
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            and node.args
        ):
            a = node.args[0]
            if (
                isinstance(a, ast.Constant)
                and isinstance(a.value, str)
                and any(ch.isdigit() for ch in a.value)
                and "%" in a.value
            ):
                issues.append(
                    LintIssue(
                        path,
                        node.lineno,
                        "C401",
                        "print of a literal string containing a percentage; "
                        "numbers must be computed and recorded with "
                        "cairn.record()",
                        severity="warning",
                    )
                )
    return issues


def lint_file(path: Path) -> list[LintIssue]:
    return lint_source(path.read_text(), path)


def lint_dir(scripts_dir: Path) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for p in sorted(scripts_dir.glob("*.py")):
        issues += lint_file(p)
    return issues
