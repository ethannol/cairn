import json
import pandas as pd
from cairn import record

x = pd.read_csv("data/raw/exposures.csv")
e = pd.read_csv("data/raw/events.csv")
buyers = set(e.loc[e.event_type == "purchase", "user_id"])
x["purchased"] = x.user_id.isin(buyers)  # zero-event users stay in the denominator
g = x.groupby("variant").purchased.agg(["mean", "count"])
for v in "AB":
    record(f"conv.{v}", float(g.loc[v, "mean"]), n=int(g.loc[v, "count"]))
    record(f"n.{v}", int(g.loc[v, "count"]), n=int(g.loc[v, "count"]))
d = (g.loc["B", "mean"] - g.loc["A", "mean"]) * 100
record("diff_pp", float(d), unit="pp", n=len(x))
json.dump({"conversion_A": float(g.loc["A", "mean"]), "conversion_B": float(g.loc["B", "mean"]),
           "diff_pp": float(d), "n_A": int(g.loc["A", "count"]), "n_B": int(g.loc["B", "count"])},
          open("answer.json", "w"))
print(g, d)

# exploratory: Wald interval for the difference (users independent, one row per user)
import numpy as np
pa, pb = g.loc["A", "mean"], g.loc["B", "mean"]
se = np.sqrt(pa*(1-pa)/g.loc["A", "count"] + pb*(1-pb)/g.loc["B", "count"])
record("diff_ci_low_pp", float((pb-pa-1.96*se)*100), unit="pp", n=len(x))
record("diff_ci_high_pp", float((pb-pa+1.96*se)*100), unit="pp", n=len(x))
record("n.total", len(x), n=len(x))
record("n.buyers", int(x.purchased.sum()), n=len(x))
