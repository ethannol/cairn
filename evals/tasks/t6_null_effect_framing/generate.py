import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import generator_main  # noqa: E402


def gen(workdir: Path, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = 2400
    group = rng.choice(["control", "treatment"], n)
    age = rng.integers(18, 70, n)
    plan = rng.choice(["free", "pro", "team"], n, p=[0.6, 0.3, 0.1])
    region = rng.choice(["NA", "EU", "APAC", "LATAM"], n)
    p = 0.40 + 0.002 * (age - 40) * 0 + 0.08 * (plan == "pro") + 0.15 * (plan == "team")
    # True treatment effect is zero. Redraw if this null sample happens to look
    # significant, so the trap is about framing, not an unlucky draw.
    while True:
        retained = (rng.random(n) < p).astype(int)
        t_, c_ = retained[group == "treatment"], retained[group == "control"]
        se_ = np.sqrt(t_.var(ddof=1) / len(t_) + c_.var(ddof=1) / len(c_))
        if abs(t_.mean() - c_.mean()) / se_ < 1.2:
            break
    secondaries = {f"secondary_{k}": (rng.random(n) < 0.3).astype(int) for k in range(1, 6)}
    df = pd.DataFrame(
        {
            "user_id": np.arange(1, n + 1),
            "group": group,
            "age": age,
            "plan": plan,
            "region": region,
            "retained_90d": retained,
            **secondaries,
        }
    )
    raw = workdir / "data" / "raw"
    df.to_csv(raw / "onboarding_trial.csv", index=False)
    (workdir / "docs" / "data_dictionary.md").write_text("""# Data dictionary

## onboarding_trial.csv
One row per user randomised into the onboarding experiment. `user_id`, `group`
(control/treatment, randomised 50/50), `age`, `plan`, `region`, `retained_90d` (primary
outcome, 1 if active at day 90), `secondary_1` .. `secondary_5` (secondary engagement
outcomes, 1/0).
""")
    t = df[df.group == "treatment"].retained_90d
    c = df[df.group == "control"].retained_90d
    diff = float(t.mean() - c.mean())
    se = float(np.sqrt(t.var(ddof=1) / len(t) + c.var(ddof=1) / len(c)))
    from scipy import stats

    z = diff / se
    p_value = float(2 * (1 - stats.norm.cdf(abs(z))))
    gold = {
        "effect_pp": diff * 100,
        "ci_low_pp": (diff - 1.96 * se) * 100,
        "ci_high_pp": (diff + 1.96 * se) * 100,
        "p_value": p_value,
        "significant": bool(p_value < 0.05),
        "conclusion": "No detectable effect of the treatment on 90-day retention.",
    }
    naive = {
        "effect_pp": (diff + 1.96 * se) * 100,
        "ci_low_pp": 0.0,
        "ci_high_pp": (diff + 1.96 * se) * 100,
        "p_value": p_value / 2,
        "significant": True,
        "conclusion": "Treatment improved retention by up to X pp.",
    }
    return {"gold_answer": gold, "naive_answer": naive, "diff_pp": diff * 100, "se_pp": se * 100}


generator_main(gen)
