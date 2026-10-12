import json
import pandas as pd
import cairn
from cairn import record

cust = pd.read_csv("data/raw/customers.csv")
seg = pd.read_csv("data/raw/customer_segments.csv")
orders = pd.read_csv("data/raw/orders.csv")

# one current-segment row per customer (latest valid_from)
assert not seg.duplicated(["customer_id", "valid_from"]).any()
cur = seg.sort_values("valid_from").groupby("customer_id", as_index=False).tail(1)
cur = cur[["customer_id", "segment"]]

cairn.join_check(orders, cust, on="customer_id", expect="m:1")
df = cairn.checked_merge(orders, cust, on="customer_id", expect="m:1", how="left")
cairn.join_check(df, cur, on="customer_id", expect="m:1")
df = cairn.checked_merge(df, cur, on="customer_id", expect="m:1", how="left")

assert len(df) == len(orders) and df.region.notna().all() and df.segment.notna().all()
total = float(orders.amount.sum())
by_r = df.groupby("region").amount.sum().to_dict()
by_s = df.groupby("segment").amount.sum().to_dict()
assert abs(sum(by_r.values()) - total) < 1e-6 and abs(sum(by_s.values()) - total) < 1e-6

record("grand_total", total, n=len(orders))
for k, v in by_r.items():
    record(f"region.{k}", float(v), n=int((df.region == k).sum()))
for k, v in by_s.items():
    record(f"segment.{k}", float(v), n=int((df.segment == k).sum()))

json.dump({"grand_total": total, "total_by_region": by_r,
           "total_by_current_segment": by_s, "n_orders": len(orders)},
          open("answer.json", "w"), indent=2)
