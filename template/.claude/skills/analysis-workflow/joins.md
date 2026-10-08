# Joins

The commonest way a clean-running analysis is wrong.

- **Fan-out.** A key that is not unique on the right side multiplies left rows. Totals and
  means inflate silently. `join_check(..., expect="m:1")` fails when the right key repeats.
- **Dropped zeros.** An inner join drops units with no matching rows. For rates and averages
  that is the "non-starters count as zero" bug: the denominator shrinks and every average
  rises. Use a left join from the population table and fill the count, not the key.
- **Match rate.** A join that matches 60% of left keys is telling you about a key format
  mismatch (leading zeros, case, whitespace, type) or a scope difference. Log it; do not
  proceed until you can explain it.
- **Null keys.** Nulls never match. Count them on both sides before joining.
- **Slowly changing attributes.** Attribute tables with validity periods (address history,
  segment history, price lists) need an as-of join, not an equality join.
- **Row count before and after.** `cairn.recount(before, after, "step", expect="same")`
  for joins that must preserve the left row count.

```python
from cairn import join_check, checked_merge, recount
join_check(orders, customers, on="customer_id", expect="m:1", min_match_rate=0.99)
df = checked_merge(orders, customers, on="customer_id", expect="m:1", how="left")
recount(orders, df, "orders+customers", expect="same")
```
