Scripts run in numeric order with `cairn run`. One step per file, each writes
its outputs to `data/derived/` or `artifacts/` and records numbers with
`cairn.record`. Keep them re-runnable from a clean state: `cairn verify`
re-executes all of them into a scratch ledger and compares.

```python
# scripts/20_analyse.py
import pandas as pd
from cairn import record, checked_merge, censored_values, unique_key

wells = pd.read_parquet("data/derived/wells.parquet")
results = pd.read_parquet("data/derived/results.parquet")
unique_key(wells, "well_id")
df = checked_merge(results, wells, on="well_id", expect="m:1", how="left")
censored_values(df["result_text"])
record("arsenic.n_wells", df["well_id"].nunique())
```
