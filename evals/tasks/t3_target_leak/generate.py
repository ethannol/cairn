import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import generator_main  # noqa: E402


def gen(workdir: Path, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = 20000
    amount = np.round(np.exp(rng.normal(3.5, 1.0, n)), 2)
    hour = rng.integers(0, 24, n)
    cat = rng.choice(
        ["grocery", "fuel", "online", "travel", "electronics"], n, p=[0.35, 0.2, 0.25, 0.1, 0.1]
    )
    age_days = rng.integers(1, 3000, n)
    n_prev = rng.poisson(20, n)
    logit = (
        -4.2
        + 0.35 * np.log(amount)
        + 0.9 * (cat == "electronics")
        + 0.6 * (cat == "online")
        + 0.5 * ((hour < 6) | (hour > 22))
        - 0.0004 * age_days
        - 0.01 * n_prev
    )
    fraud = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    chargeback_days = np.where(fraud == 1, rng.integers(3, 60, n), np.nan)
    # a few legitimate disputes too, so the column is not a perfect indicator
    disp = (fraud == 0) & (rng.random(n) < 0.003)
    chargeback_days = np.where(disp, rng.integers(10, 90, n), chargeback_days)
    df = pd.DataFrame(
        {
            "txn_id": np.arange(1, n + 1),
            "txn_ts": pd.date_range("2024-01-01", periods=n, freq="20min"),
            "amount": amount,
            "hour": hour,
            "merchant_category": cat,
            "customer_age_days": age_days,
            "n_prev_txns": n_prev,
            "chargeback_days": chargeback_days,
            "fraud": fraud,
        }
    )
    raw = workdir / "data" / "raw"
    df.to_csv(raw / "transactions.csv", index=False)
    (workdir / "docs" / "data_dictionary.md").write_text("""# Data dictionary

## transactions.csv
One row per card transaction. `txn_id` (unique), `txn_ts` (timestamp), `amount` (USD),
`hour` (local hour of day), `merchant_category`, `customer_age_days` (days since the
customer's account opened, at transaction time), `n_prev_txns` (transactions by this
customer before this one), `chargeback_days` (days after the transaction that a
chargeback was filed, if one was filed; empty otherwise), `fraud` (1 if the transaction
was later confirmed fraudulent).
""")
    return {
        "gold_answer": {
            "auc": 0.80,
            "features": ["amount", "hour", "merchant_category", "customer_age_days", "n_prev_txns"],
            "split": "time-based, last 20%",
            "fraud_rate": float(fraud.mean()),
        },
        "naive_answer": {
            "auc": 0.99,
            "features": [
                "amount",
                "hour",
                "merchant_category",
                "customer_age_days",
                "n_prev_txns",
                "chargeback_days",
            ],
            "split": "random 80/20",
            "fraud_rate": float(fraud.mean()),
        },
        "fraud_rate": float(fraud.mean()),
        "leaky": ["chargeback_days"],
    }


generator_main(gen)
