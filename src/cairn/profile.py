"""Profile raw tables before any analysis.

Writes `profiles/<name>.json` and `profiles/<name>.md`. The point is to make
row grain, candidate keys, null rates, and censoring markers visible before
the agent joins or summarises anything.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cairn.checks import CENSOR_MARKERS, file_sha256


def read_table(path: Path, *, nrows: int | None = None) -> pd.DataFrame:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".csv", ".txt", ".tsv"):
        sep = "\t" if suffix == ".tsv" else ","
        return pd.read_csv(p, sep=sep, nrows=nrows, low_memory=False)
    if suffix in (".parquet", ".pq"):
        return pd.read_parquet(p)
    if suffix in (".json", ".jsonl"):
        return pd.read_json(p, lines=suffix == ".jsonl", nrows=nrows)
    raise ValueError(f"unsupported table format: {p.suffix}")


def _col_profile(s: pd.Series) -> dict[str, Any]:
    n = len(s)
    nulls = int(s.isna().sum())
    nunique = int(s.nunique(dropna=True))
    out: dict[str, Any] = {
        "dtype": str(s.dtype),
        "null_count": nulls,
        "null_rate": round(nulls / n, 6) if n else 0.0,
        "n_unique": nunique,
        "unique_rate": round(nunique / max(n - nulls, 1), 6),
    }
    non_null = s.dropna()
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        if len(non_null):
            q = non_null.quantile([0, 0.05, 0.5, 0.95, 1]).tolist()
            out["numeric"] = {
                "min": q[0],
                "p05": q[1],
                "median": q[2],
                "p95": q[3],
                "max": q[4],
                "mean": float(non_null.mean()),
                "zeros": int((non_null == 0).sum()),
                "negatives": int((non_null < 0).sum()),
            }
    else:
        as_str = non_null.astype("string").str.strip()
        lt = int(as_str.str.startswith("<").sum())
        markers = int(as_str.str.lower().isin(CENSOR_MARKERS).sum())
        numeric_like = pd.to_numeric(as_str, errors="coerce").notna().sum()
        out["top_values"] = {str(k): int(v) for k, v in non_null.value_counts().head(8).items()}
        if lt or markers:
            out["censoring_markers"] = {"lt_prefixed": lt, "markers": markers}
        if len(as_str) and numeric_like / len(as_str) > 0.5 and numeric_like < len(as_str):
            out["mixed_numeric_text"] = {
                "numeric_like": int(numeric_like),
                "non_numeric": int(len(as_str) - numeric_like),
                "non_numeric_examples": as_str[pd.to_numeric(as_str, errors="coerce").isna()]
                .drop_duplicates()
                .head(5)
                .tolist(),
            }
        parsed = pd.to_datetime(as_str, errors="coerce", format="mixed") if len(as_str) else None
        if parsed is not None and parsed.notna().mean() > 0.9:
            out["datetime"] = {"min": str(parsed.min()), "max": str(parsed.max())}
    return out


def _candidate_keys(df: pd.DataFrame, max_combo: int = 2, max_cols: int = 12) -> list[list[str]]:
    cols = [c for c in df.columns if df[c].notna().all() and df[c].nunique() > 1]
    singles = [[c] for c in cols if not df.duplicated([c]).any()]
    if singles or len(df) < 2:
        return singles
    cols = sorted(cols, key=lambda c: -df[c].nunique())[:max_cols]
    pairs = [list(p) for p in combinations(cols, max_combo) if not df.duplicated(list(p)).any()]
    return pairs[:5]


def profile_table(df: pd.DataFrame, name: str, *, source: Path | None = None) -> dict[str, Any]:
    prof: dict[str, Any] = {
        "name": name,
        "source": str(source) if source else None,
        "sha256": file_sha256(source) if source and Path(source).is_file() else None,
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "duplicate_rows": int(df.duplicated().sum()),
        "candidate_keys": _candidate_keys(df),
        "fields": {str(c): _col_profile(df[c]) for c in df.columns},
    }
    return prof


def to_markdown(prof: dict[str, Any]) -> str:
    lines = [f"# Profile: {prof['name']}", ""]
    if prof.get("source"):
        lines.append(f"Source: `{prof['source']}` (sha256 `{(prof.get('sha256') or '')[:12]}`)")
    lines += [
        f"Rows: {prof['rows']}  Columns: {prof['columns']}  "
        f"Exact duplicate rows: {prof['duplicate_rows']}",
        f"Candidate keys: {prof['candidate_keys'] or 'NONE FOUND (what does one row represent?)'}",
        "",
        "| field | dtype | nulls | unique | notes |",
        "|---|---|---|---|---|",
    ]
    for col, f in prof["fields"].items():
        notes = []
        if "numeric" in f:
            q = f["numeric"]
            notes.append(f"min {q['min']:g}, median {q['median']:g}, max {q['max']:g}")
            if q["negatives"]:
                notes.append(f"{q['negatives']} negative")
        if "censoring_markers" in f:
            notes.append(f"CENSORED: {f['censoring_markers']}")
        if "mixed_numeric_text" in f:
            notes.append(f"mixed numeric/text: {f['mixed_numeric_text']['non_numeric_examples']}")
        if "datetime" in f:
            notes.append(f"dates {f['datetime']['min'][:10]} to {f['datetime']['max'][:10]}")
        if "top_values" in f and "datetime" not in f:
            top = list(f["top_values"].items())[:3]
            notes.append("top: " + ", ".join(f"{k}({v})" for k, v in top))
        lines.append(
            f"| {col} | {f['dtype']} | {f['null_rate']:.1%} | {f['n_unique']} | "
            f"{'; '.join(notes)} |"
        )
    return "\n".join(lines) + "\n"


def profile_files(paths: list[Path], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for p in paths:
        df = read_table(p)
        prof = profile_table(df, p.stem, source=p)
        jp = out_dir / f"{p.stem}.json"
        mp = out_dir / f"{p.stem}.md"
        jp.write_text(json.dumps(prof, indent=2, default=_jsonable) + "\n")
        mp.write_text(to_markdown(prof))
        written += [jp, mp]
    return written


def _jsonable(x: Any) -> Any:
    if isinstance(x, np.generic):
        return x.item()
    return str(x)
