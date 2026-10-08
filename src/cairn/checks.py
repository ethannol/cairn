"""Deterministic data checks.

Each check returns a `CheckResult` and appends a JSON line to
`artifacts/checks.jsonl` (override with $CAIRN_CHECKS). `cairn verify` fails
if any recorded check failed, and the analysis-workflow skill tells the agent
to run these before trusting a join, a split, or a summary statistic.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

CHECKS_ENV = "CAIRN_CHECKS"
CENSOR_MARKERS = {"nd", "n.d.", "bdl", "u", "<dl", "<mdl", "<rl", "non-detect", "nondetect", "dl"}


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    severity: Literal["error", "warning", "info"] = "error"
    source: str = ""
    recorded_at: str = ""

    def __bool__(self) -> bool:
        return self.passed

    def __str__(self) -> str:
        tag = "PASS" if self.passed else ("WARN" if self.severity == "warning" else "FAIL")
        return f"[{tag}] {self.name}: {self.message}"


def _checks_path() -> Path:
    env = os.environ.get(CHECKS_ENV)
    if env:
        return Path(env)
    from cairn.config import find_root

    root = find_root()
    base = root if root is not None else Path.cwd()
    return base / "artifacts" / "checks.jsonl"


def _source() -> str:
    main = sys.modules.get("__main__")
    f = getattr(main, "__file__", None)
    return Path(f).name if f else "<interactive>"


def _emit(result: CheckResult, *, quiet: bool) -> CheckResult:
    result.source = result.source or _source()
    result.recorded_at = datetime.now(UTC).isoformat(timespec="seconds")
    path = _checks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(asdict(result), default=str) + "\n")
    if not quiet:
        print(str(result))
    return result


def read_checks(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or _checks_path()
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Keys and joins
# ---------------------------------------------------------------------------


def unique_key(
    df: pd.DataFrame, key: str | list[str], *, name: str | None = None, quiet: bool = False
) -> CheckResult:
    """Is `key` unique in `df`? Reports duplicated rows and examples."""
    keys = [key] if isinstance(key, str) else list(key)
    dup = df.duplicated(keys, keep=False)
    n_dup = int(dup.sum())
    examples = df.loc[dup, keys].drop_duplicates().head(5).to_dict("records")
    return _emit(
        CheckResult(
            name=name or f"unique_key({'+'.join(keys)})",
            passed=n_dup == 0,
            message=(
                f"{len(df)} rows, {n_dup} rows share a duplicated key"
                + (f"; e.g. {examples[0]}" if examples else "")
            ),
            details={
                "key": keys,
                "rows": int(len(df)),
                "duplicated_rows": n_dup,
                "examples": examples,
            },
        ),
        quiet=quiet,
    )


def _cardinality(left: pd.DataFrame, right: pd.DataFrame, lk: list[str], rk: list[str]) -> str:
    lu = not left.duplicated(lk).any()
    ru = not right.duplicated(rk).any()
    return {(True, True): "1:1", (True, False): "1:m", (False, True): "m:1", (False, False): "m:m"}[
        (lu, ru)
    ]


def join_check(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on: str | list[str] | None = None,
    *,
    left_on: str | list[str] | None = None,
    right_on: str | list[str] | None = None,
    how: str = "left",
    expect: Literal["1:1", "1:m", "m:1", "m:m"] | None = "m:1",
    max_fanout: float = 1.0,
    min_match_rate: float | None = None,
    name: str | None = None,
    quiet: bool = False,
) -> CheckResult:
    """Describe what a merge WOULD do: cardinality, match rate, fan-out.

    Fails when the observed cardinality is stricter-violating than `expect`
    (e.g. expected m:1 but right key is not unique) or when rows multiply by
    more than `max_fanout`. Use before any merge whose result feeds a number.
    """
    lk = (
        [on]
        if isinstance(on, str)
        else list(on)
        if on
        else ([left_on] if isinstance(left_on, str) else list(left_on))
    )
    rk = (
        [on]
        if isinstance(on, str)
        else list(on)
        if on
        else ([right_on] if isinstance(right_on, str) else list(right_on))
    )
    observed = _cardinality(left, right, lk, rk)
    lkeys = left[lk].drop_duplicates()
    rkeys = right[rk].drop_duplicates()
    rkeys_renamed = rkeys.set_axis(lk, axis=1)
    matched_keys = lkeys.merge(rkeys_renamed, on=lk, how="inner")
    left_key_match_rate = len(matched_keys) / max(len(lkeys), 1)
    left_rows_matched = left.merge(rkeys_renamed.assign(_m=1), on=lk, how="left")["_m"].notna()
    row_match_rate = float(left_rows_matched.mean()) if len(left) else 0.0
    right_counts = right.groupby(rk, dropna=False).size()
    sizes = left.merge(
        right_counts.rename("_n").reset_index().set_axis([*lk, "_n"], axis=1), on=lk, how="left"
    )["_n"].fillna(0 if how == "inner" else 1)
    rows_after = int(sizes.sum()) if how in ("left", "inner") else None
    fanout = (rows_after / len(left)) if rows_after is not None and len(left) else 1.0
    null_keys_left = int(left[lk].isna().any(axis=1).sum())
    null_keys_right = int(right[rk].isna().any(axis=1).sum())
    unmatched = lkeys.merge(rkeys_renamed, on=lk, how="left", indicator=True)
    unmatched = unmatched[unmatched["_merge"] == "left_only"][lk].head(5).to_dict("records")

    problems: list[str] = []
    if expect is not None:
        ok = {
            "1:1": observed == "1:1",
            "1:m": observed in ("1:1", "1:m"),
            "m:1": observed in ("1:1", "m:1"),
            "m:m": True,
        }[expect]
        if not ok:
            problems.append(f"expected {expect} but keys are {observed}")
    if fanout > max_fanout + 1e-12:
        problems.append(f"rows would multiply x{fanout:.3f} (> {max_fanout})")
    if min_match_rate is not None and row_match_rate < min_match_rate:
        problems.append(f"row match rate {row_match_rate:.3%} < {min_match_rate:.0%}")

    msg = (
        f"{observed} on {lk}; {row_match_rate:.1%} of left rows match, "
        f"{left_key_match_rate:.1%} of left keys match; rows {len(left)} -> {rows_after}"
        + (
            f"; null keys L={null_keys_left} R={null_keys_right}"
            if null_keys_left or null_keys_right
            else ""
        )
        + (f"; PROBLEMS: {'; '.join(problems)}" if problems else "")
    )
    return _emit(
        CheckResult(
            name=name or f"join_check({'+'.join(lk)})",
            passed=not problems,
            message=msg,
            details={
                "left_keys": lk,
                "right_keys": rk,
                "how": how,
                "observed": observed,
                "expected": expect,
                "rows_before": int(len(left)),
                "rows_after": rows_after,
                "fanout": round(fanout, 6),
                "row_match_rate": round(row_match_rate, 6),
                "key_match_rate": round(left_key_match_rate, 6),
                "null_keys_left": null_keys_left,
                "null_keys_right": null_keys_right,
                "unmatched_examples": unmatched,
            },
        ),
        quiet=quiet,
    )


def checked_merge(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *args: Any,
    expect: Literal["1:1", "1:m", "m:1", "m:m"] | None = "m:1",
    max_fanout: float = 1.0,
    min_match_rate: float | None = None,
    name: str | None = None,
    **kwargs: Any,
) -> pd.DataFrame:
    """`pd.merge` that runs `join_check` first and raises if it fails."""
    on = args[0] if args else kwargs.get("on")
    res = join_check(
        left,
        right,
        on,
        how=kwargs.get("how", "inner"),
        left_on=kwargs.get("left_on"),
        right_on=kwargs.get("right_on"),
        expect=expect,
        max_fanout=max_fanout,
        min_match_rate=min_match_rate,
        name=name,
    )
    if not res.passed:
        raise ValueError(f"checked_merge refused: {res.message}")
    if expect in ("1:1", "1:m", "m:1") and "validate" not in kwargs:
        kwargs["validate"] = {"1:1": "one_to_one", "1:m": "one_to_many", "m:1": "many_to_one"}[
            expect
        ]
    return left.merge(right, *args, **kwargs)


# ---------------------------------------------------------------------------
# Row accounting
# ---------------------------------------------------------------------------


def recount(
    before: pd.DataFrame | int,
    after: pd.DataFrame | int,
    step: str,
    *,
    expect: Literal["same", "fewer", "more", "any"] = "any",
    quiet: bool = False,
) -> CheckResult:
    """Record the row count before and after a step. Fails if direction violates `expect`."""
    nb = before if isinstance(before, int) else len(before)
    na = after if isinstance(after, int) else len(after)
    ok = {"same": na == nb, "fewer": na <= nb, "more": na >= nb, "any": True}[expect]
    return _emit(
        CheckResult(
            name=f"recount({step})",
            passed=ok,
            message=f"{nb} -> {na} rows ({na - nb:+d}, {((na / nb) - 1) if nb else 0:+.1%})",
            details={"before": nb, "after": na, "expect": expect},
        ),
        quiet=quiet,
    )


def denominator(
    numerator_df: pd.DataFrame | int,
    population_df: pd.DataFrame | int,
    metric: str,
    *,
    population_desc: str,
    quiet: bool = False,
) -> CheckResult:
    """Make the denominator of a rate explicit. Always passes; records the population."""
    n = numerator_df if isinstance(numerator_df, int) else len(numerator_df)
    d = population_df if isinstance(population_df, int) else len(population_df)
    rate = (n / d) if d else float("nan")
    return _emit(
        CheckResult(
            name=f"denominator({metric})",
            passed=True,
            severity="info",
            message=f"{metric} = {n} / {d} ({population_desc}) = {rate:.4f}",
            details={"numerator": n, "denominator": d, "population": population_desc},
        ),
        quiet=quiet,
    )


# ---------------------------------------------------------------------------
# Leakage
# ---------------------------------------------------------------------------


def _row_hashes(df: pd.DataFrame, cols: list[str] | None) -> pd.Series:
    sub = df[cols] if cols else df
    return pd.util.hash_pandas_object(sub, index=False)


def split_overlap(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    key: str | list[str] | None = None,
    cols: list[str] | None = None,
    quiet: bool = False,
) -> CheckResult:
    """Share of test rows (or test keys) that also appear in train. Fails if > 0."""
    if key is not None:
        keys = [key] if isinstance(key, str) else list(key)
        tr = set(map(tuple, train[keys].drop_duplicates().itertuples(index=False)))
        te = test[keys].drop_duplicates()
        overlap = sum(tuple(r) in tr for r in te.itertuples(index=False))
        share = overlap / max(len(te), 1)
        what = f"test keys {keys}"
    else:
        tr = set(_row_hashes(train, cols))
        te_h = _row_hashes(test, cols)
        overlap = int(te_h.isin(tr).sum())
        share = overlap / max(len(test), 1)
        what = "test rows"
    return _emit(
        CheckResult(
            name="split_overlap",
            passed=overlap == 0,
            message=f"{overlap} of {what} ({share:.2%}) also appear in train",
            details={"overlap": int(overlap), "share": round(share, 6), "key": key, "cols": cols},
        ),
        quiet=quiet,
    )


def time_leak(
    train: pd.DataFrame, test: pd.DataFrame, time_col: str, *, quiet: bool = False
) -> CheckResult:
    """For a temporal split, every train timestamp must precede every test timestamp."""
    tmax = pd.to_datetime(train[time_col]).max()
    tmin = pd.to_datetime(test[time_col]).min()
    ok = bool(tmax < tmin)
    return _emit(
        CheckResult(
            name=f"time_leak({time_col})",
            passed=ok,
            message=f"train max {tmax} {'<' if ok else '>='} test min {tmin}",
            details={"train_max": str(tmax), "test_min": str(tmin)},
        ),
        quiet=quiet,
    )


def target_proxy(
    df: pd.DataFrame,
    target: str,
    *,
    threshold: float = 0.95,
    exclude: list[str] | None = None,
    quiet: bool = False,
) -> CheckResult:
    """Columns that predict the target suspiciously well on their own.

    Flags any column whose non-null pattern or value separates the target with
    accuracy >= `threshold` (binary targets) or |corr| >= `threshold` (numeric).
    A warning, not a failure: the agent must justify keeping a flagged column.
    """
    y = df[target]
    flagged: dict[str, float] = {}
    binary = y.dropna().nunique() == 2
    for col in df.columns:
        if col == target or (exclude and col in exclude):
            continue
        s = df[col]
        scores: list[float] = []
        if s.isna().any() and not s.isna().all() and binary:
            m = s.isna().astype(int)
            acc = max((m == y.astype(int)).mean(), (m != y.astype(int)).mean())
            scores.append(float(acc))
        if pd.api.types.is_numeric_dtype(s) and s.notna().sum() > 2:
            try:
                c = abs(
                    float(np.corrcoef(s.fillna(s.median()).astype(float), y.astype(float))[0, 1])
                )
                if not np.isnan(c):
                    scores.append(c)
            except (TypeError, ValueError):
                pass
        if scores and max(scores) >= threshold:
            flagged[col] = round(max(scores), 4)
    return _emit(
        CheckResult(
            name=f"target_proxy({target})",
            passed=not flagged,
            severity="warning",
            message=(
                f"suspicious columns: {flagged}"
                if flagged
                else f"no single column reaches {threshold:.0%} agreement with the target"
            ),
            details={"flagged": flagged, "threshold": threshold},
        ),
        quiet=quiet,
    )


# ---------------------------------------------------------------------------
# Censored / non-detect values
# ---------------------------------------------------------------------------


def censored_values(
    series: pd.Series,
    *,
    limit_col: pd.Series | None = None,
    name: str | None = None,
    quiet: bool = False,
) -> CheckResult:
    """Detect non-detect markers in a result column ('<0.5', 'ND', 'U', NaN with limit).

    Always passes with severity=warning when censoring is present: the point
    is to force the analyst to state how censored values are handled.
    """
    s = series.astype("string").str.strip()
    lt = s.str.startswith("<").fillna(False).astype(bool)
    marker = s.str.lower().isin(CENSOR_MARKERS).fillna(False).astype(bool)
    numeric = pd.to_numeric(s.str.lstrip("<"), errors="coerce")
    non_numeric_other = (s.notna() & numeric.isna()).fillna(False).astype(bool) & ~marker & ~lt
    with_limit = pd.Series(False, index=series.index)
    if limit_col is not None:
        with_limit = series.isna() & limit_col.notna()
    censored = lt | marker | with_limit
    n_c = int(censored.sum())
    return _emit(
        CheckResult(
            name=name or f"censored_values({series.name})",
            passed=True,
            severity="warning" if n_c else "info",
            message=(
                f"{n_c} of {len(series)} ({n_c / max(len(series), 1):.1%}) censored: "
                f"{int(lt.sum())} '<' prefixed, {int(marker.sum())} markers, "
                f"{int(with_limit.sum())} null-with-limit; {int(non_numeric_other.sum())} "
                f"other non-numeric. Do not substitute 0, the limit, or half the limit as the "
                f"main method."
            ),
            details={
                "n": int(len(series)),
                "censored": n_c,
                "lt_prefixed": int(lt.sum()),
                "markers": int(marker.sum()),
                "null_with_limit": int(with_limit.sum()),
                "other_non_numeric": int(non_numeric_other.sum()),
                "examples": s[censored].drop_duplicates().head(5).tolist(),
            },
        ),
        quiet=quiet,
    )


def parse_censored(series: pd.Series) -> pd.DataFrame:
    """Split a result column into (value, censored, limit) for censored methods."""
    s = series.astype("string").str.strip()
    lt = s.str.startswith("<").fillna(False).astype(bool)
    marker = s.str.lower().isin(CENSOR_MARKERS).fillna(False).astype(bool)
    value = pd.to_numeric(s.str.lstrip("<"), errors="coerce").astype("float64")
    out = pd.DataFrame(
        {"value": value.where(~lt & ~marker), "censored": lt | marker, "limit": value.where(lt)}
    )
    return out


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
