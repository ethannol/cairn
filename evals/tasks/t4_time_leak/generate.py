import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import generator_main  # noqa: E402


def gen(workdir: Path, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n_cust, months = 1500, pd.period_range("2023-01", "2024-12", freq="M")
    rows = []
    for cid in range(1, n_cust + 1):
        base = rng.gamma(3, 10)
        tenure = 0
        for m in months:
            tenure += 1
            usage = max(0.0, base + rng.normal(0, 5) - 0.3 * tenure)
            tickets = rng.poisson(0.3 + (usage < 10) * 0.8)
            p = 1 / (1 + np.exp(-(-3.0 - 0.05 * usage + 0.6 * tickets + 0.02 * tenure)))
            churn = int(rng.random() < p)
            rows.append(
                {
                    "customer_id": cid,
                    "month": str(m),
                    "usage_hours": round(usage, 1),
                    "support_tickets": tickets,
                    "tenure_months": tenure,
                    "churned_next_month": churn,
                }
            )
            if churn:
                break
    df = pd.DataFrame(rows)
    # future information: usage in the following month, backfilled (0 after churn)
    df = df.sort_values(["customer_id", "month"])
    df["next_month_usage"] = df.groupby("customer_id")["usage_hours"].shift(-1).fillna(0.0)
    df.loc[df.churned_next_month == 1, "next_month_usage"] = 0.0
    raw = workdir / "data" / "raw"
    df.sample(frac=1, random_state=seed).to_csv(raw / "churn_monthly.csv", index=False)
    (workdir / "docs" / "data_dictionary.md").write_text("""# Data dictionary

## churn_monthly.csv
One row per customer per month while the customer is active. `customer_id`, `month`
(YYYY-MM), `usage_hours` (usage during that month), `support_tickets` (tickets opened that
month), `tenure_months`, `next_month_usage` (usage hours in the following month, backfilled
from the next record; 0 if the customer churned), `churned_next_month` (1 if the customer
churned in the following month; this is the prediction target).
""")
    test_months = [str(m) for m in months[-3:]]
    n_test = int(df.month.isin(test_months).sum())
    return {
        "gold_answer": {
            "train_end": str(months[-4]),
            "test_start": test_months[0],
            "n_test": n_test,
            "test_auc": 0.72,
            "features": ["usage_hours", "support_tickets", "tenure_months"],
        },
        "naive_answer": {
            "train_end": str(months[-1]),
            "test_start": str(months[0]),
            "n_test": int(len(df) * 0.2),
            "test_auc": 0.99,
            "features": ["usage_hours", "support_tickets", "tenure_months", "next_month_usage"],
        },
        "test_months": test_months,
        "n_test": n_test,
        "leaky": ["next_month_usage"],
    }


generator_main(gen)
