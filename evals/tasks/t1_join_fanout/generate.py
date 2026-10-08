import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import generator_main  # noqa: E402


def gen(workdir: Path, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n_cust, n_orders = 1000, 5000
    regions = rng.choice(["north", "south", "east", "west"], n_cust, p=[0.3, 0.3, 0.2, 0.2])
    customers = pd.DataFrame({"customer_id": np.arange(1, n_cust + 1), "region": regions})
    # segment history: 1-3 rows per customer, with valid_from dates
    rows = []
    for cid in customers.customer_id:
        k = rng.choice([1, 2, 3], p=[0.4, 0.4, 0.2])
        dates = sorted(
            rng.choice(pd.date_range("2022-01-01", "2024-06-30").to_numpy(), k, replace=False)
        )
        segs = rng.choice(["basic", "plus", "premium"], k)
        for d, s in zip(dates, segs, strict=True):
            rows.append({"customer_id": cid, "segment": s, "valid_from": pd.Timestamp(d).date()})
    seg_hist = pd.DataFrame(rows)
    orders = pd.DataFrame(
        {
            "order_id": np.arange(1, n_orders + 1),
            "customer_id": rng.integers(1, n_cust + 1, n_orders),
            "order_date": rng.choice(
                pd.date_range("2024-01-01", "2024-12-31").to_numpy(), n_orders
            ),
            "amount": np.round(rng.gamma(2.0, 40.0, n_orders), 2),
        }
    )
    orders["order_date"] = pd.to_datetime(orders["order_date"]).dt.date
    raw = workdir / "data" / "raw"
    customers.to_csv(raw / "customers.csv", index=False)
    seg_hist.sample(frac=1, random_state=seed).to_csv(raw / "customer_segments.csv", index=False)
    orders.to_csv(raw / "orders.csv", index=False)
    (workdir / "docs" / "data_dictionary.md").write_text("""# Data dictionary

## customers.csv
One row per customer. `customer_id` (int, unique), `region` (north/south/east/west).

## customer_segments.csv
Segment assignment history. One row per (customer_id, valid_from); a customer can have
several rows as their segment changed over time. `segment` in basic/plus/premium.
The current segment is the row with the latest `valid_from`.

## orders.csv
One row per order in 2024. `order_id` (unique), `customer_id`, `order_date`, `amount` (USD).
""")
    current = (
        seg_hist.sort_values("valid_from")
        .groupby("customer_id")
        .tail(1)[["customer_id", "segment"]]
    )
    df = orders.merge(customers, on="customer_id", validate="m:1").merge(
        current, on="customer_id", validate="m:1"
    )
    gold = {
        "grand_total": round(float(orders.amount.sum()), 2),
        "total_by_region": {
            k: round(float(v), 2) for k, v in df.groupby("region").amount.sum().items()
        },
        "total_by_current_segment": {
            k: round(float(v), 2) for k, v in df.groupby("segment").amount.sum().items()
        },
        "n_orders": int(len(orders)),
    }
    naive_df = orders.merge(customers, on="customer_id").merge(seg_hist, on="customer_id")
    naive = {
        "grand_total": round(float(naive_df.amount.sum()), 2),
        "total_by_region": {
            k: round(float(v), 2) for k, v in naive_df.groupby("region").amount.sum().items()
        },
        "total_by_current_segment": {
            k: round(float(v), 2) for k, v in naive_df.groupby("segment").amount.sum().items()
        },
        "n_orders": int(len(naive_df)),
    }
    return {"gold_answer": gold, "naive_answer": naive}


generator_main(gen)
