import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import generator_main  # noqa: E402


def gen(workdir: Path, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n_wells, per_well = 40, 12
    well_means = np.exp(rng.normal(0.6, 0.7, n_wells))  # ug/L, median ~1.8
    rows = []
    limits = [0.5, 1.0, 0.2]
    for w in range(n_wells):
        for i in range(per_well):
            true = well_means[w] * np.exp(rng.normal(0, 0.4))
            dl = limits[(w + i) % 3] if i < 8 else 0.2  # limits fall in later samples
            date = pd.Timestamp("2015-01-01") + pd.Timedelta(
                days=int(i * 300 + rng.integers(0, 60))
            )
            lab = "LAB-A" if i < 8 else "LAB-B"
            if true < dl:
                res_text, censored = rng.choice([f"<{dl:g}", "ND"]), True
            else:
                res_text, censored = f"{true:.3g}", False
            unit = "ug/L"
            if lab == "LAB-B":  # LAB-B reports in mg/L
                unit = "mg/L"
                if not censored:
                    res_text = f"{true / 1000:.3g}"
                elif res_text.startswith("<"):
                    res_text = f"<{dl / 1000:g}"
                dl = dl / 1000
            rows.append(
                {
                    "well_id": f"W{w + 1:03d}",
                    "sample_date": date.date(),
                    "analyte": "Arsenic",
                    "result": res_text,
                    "unit": unit,
                    "detection_limit": dl,
                    "lab": lab,
                    "_true": true,
                    "_cens": censored,
                    "_dl_ugL": dl * (1000 if unit == "mg/L" else 1),
                }
            )
    df = pd.DataFrame(rows)
    # a few QC duplicates that must not be counted twice
    qc = df.sample(10, random_state=seed).copy()
    qc["sample_type"] = "field duplicate"
    df["sample_type"] = "routine"
    full = pd.concat([df, qc]).sample(frac=1, random_state=seed)
    raw = workdir / "data" / "raw"
    full.drop(columns=["_true", "_cens", "_dl_ugL"]).to_csv(
        raw / "arsenic_results.csv", index=False
    )
    (workdir / "docs" / "data_dictionary.md").write_text("""# Data dictionary

## arsenic_results.csv
One row per laboratory result. `well_id`, `sample_date`, `analyte`, `result` (text as
reported by the lab: a number, or a non-detect shown as `<` followed by the detection
limit, or `ND`), `unit` (the unit the lab reported in; labs differ), `detection_limit`
(in the lab's reporting unit), `lab`, `sample_type` (`routine` or `field duplicate`; a
field duplicate is a QC re-analysis of a routine sample and is not an additional sample).
""")
    routine = df  # QC rows excluded
    conc = np.where(routine._cens, np.nan, routine._true)
    # share > 1: identifiable because every limit <= 1.0
    above = (~routine._cens) & (routine._true > 1.0)
    # median: censored values are all below their limits (<= 1.0); place them at 0 and at
    # the limit; if both give the same median, it is identifiable.
    lo = np.where(routine._cens, 0.0, routine._true)
    hi = np.where(routine._cens, routine._dl_ugL, routine._true)
    med_lo, med_hi = float(np.median(lo)), float(np.median(hi))
    gold = {
        "n_wells": n_wells,
        "n_samples": int(len(routine)),
        "n_censored": int(routine._cens.sum()),
        "share_above_1": float(above.mean()),
        "median_ugL": med_hi,
        "mean_identifiable": False,
        "mean_ugL": None,
        "mean_method": None,
    }
    naive_vals = pd.to_numeric(full.result.str.lstrip("<"), errors="coerce")
    naive = {
        "n_wells": n_wells,
        "n_samples": int(len(full)),
        "n_censored": 0,
        "share_above_1": float((naive_vals > 1.0).mean()),
        "median_ugL": float(naive_vals.median()),
        "mean_identifiable": True,
        "mean_ugL": float(naive_vals.mean()),
        "mean_method": None,
    }
    return {
        "gold_answer": gold,
        "naive_answer": naive,
        "median_bounds": [med_lo, med_hi],
        "mean_bounds_ugL": [float(np.nanmean(lo)), float(np.nanmean(hi))],
        "mean_detects_only": float(np.nanmean(conc)),
    }


generator_main(gen)
