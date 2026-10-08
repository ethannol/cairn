# Leakage and selection

- **Split first.** Fit scalers, imputers, encoders, feature selection, and target encodings
  on the training rows only. `fit_transform(X)` on the full frame is leakage.
- **Time.** If rows have a time order, split by time. `cairn.time_leak(train, test, "date")`
  must pass. Rolling features must use only past rows.
- **Duplicates across splits.** `cairn.split_overlap(train, test, key="customer_id")`.
  The same unit on both sides of a split inflates every metric.
- **Target proxies.** Columns recorded after the outcome (refund date, chargeback flag,
  resolution code, days_to_event) or that are only populated when the target is positive.
  `cairn.target_proxy(df, "target")` flags columns that alone reach 95% agreement. Drop or
  justify each flagged column in `docs/decisions.md`.
- **Selection on the test set.** Choose models and thresholds on validation. Evaluate on
  the holdout once and report that number. If you iterated against the holdout, say so;
  the reported metric is then optimistic.
- **Null-effect honesty.** If the pre-registered estimate's interval includes zero, the
  answer is "no detectable effect". Reframing as an "upper bound", changing the outcome,
  subsetting, or switching tests after seeing results is exploratory and labelled.
