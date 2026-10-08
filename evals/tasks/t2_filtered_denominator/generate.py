import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import generator_main  # noqa: E402


def gen(workdir: Path, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = 10000
    users = pd.DataFrame(
        {
            "user_id": np.arange(1, n + 1),
            "variant": rng.choice(["A", "B"], n),
            "exposed_at": rng.choice(
                pd.date_range("2024-03-01", "2024-03-14", freq="h").to_numpy(), n
            ),
        }
    )
    p_any = {"A": 0.55, "B": 0.62}  # share of users with any event
    p_buy_given_any = {"A": 0.12, "B": 0.11}  # B gets more browsers but not more buyers
    rows = []
    exposed_at = pd.to_datetime(users.exposed_at)
    for uid, v, t0 in zip(users.user_id, users.variant, exposed_at, strict=True):
        if rng.random() < p_any[v]:
            # every event happens after the user's exposure, so "purchased after
            # exposure" and "purchased" are the same population
            for _ in range(int(rng.integers(1, 5))):
                rows.append(
                    {
                        "user_id": uid,
                        "event_type": "view",
                        "ts": t0 + pd.Timedelta(minutes=int(rng.integers(1, 14 * 24 * 60))),
                    }
                )
            if rng.random() < p_buy_given_any[v]:
                rows.append(
                    {
                        "user_id": uid,
                        "event_type": "purchase",
                        "ts": t0 + pd.Timedelta(minutes=int(rng.integers(1, 14 * 24 * 60))),
                    }
                )
    events = pd.DataFrame(rows)
    raw = workdir / "data" / "raw"
    users.to_csv(raw / "exposures.csv", index=False)
    events.sample(frac=1, random_state=seed).to_csv(raw / "events.csv", index=False)
    (workdir / "docs" / "data_dictionary.md").write_text("""# Data dictionary

## exposures.csv
One row per user exposed to the experiment. `user_id` (unique), `variant` (A or B),
`exposed_at` (timestamp of first exposure).

## events.csv
One row per event in the event stream during the experiment window. `user_id`,
`event_type` (view or purchase), `ts`. Users with no events do not appear in this file.
""")
    buyers = set(events.loc[events.event_type == "purchase", "user_id"])
    gold, naive = {}, {}
    for v in ("A", "B"):
        exposed = users.loc[users.variant == v, "user_id"]
        n_buy = int(exposed.isin(buyers).sum())
        gold[f"conversion_{v}"] = n_buy / len(exposed)
        gold[f"n_{v}"] = int(len(exposed))
        active = exposed[exposed.isin(set(events.user_id))]
        naive[f"conversion_{v}"] = n_buy / len(active)
        naive[f"n_{v}"] = int(len(active))
    gold["diff_pp"] = (gold["conversion_B"] - gold["conversion_A"]) * 100
    naive["diff_pp"] = (naive["conversion_B"] - naive["conversion_A"]) * 100
    return {"gold_answer": gold, "naive_answer": naive}


generator_main(gen)
