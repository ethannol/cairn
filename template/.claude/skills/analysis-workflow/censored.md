# Censored and non-detect values

Environmental, clinical, and sensor data report values below a detection or reporting
limit as `<0.5`, `ND`, `U`, a blank with a limit column, or a flagged value. Treating any of
these as a measurement produces a biased summary that looks precise.

- Detect them: `cairn.censored_values(df["result"], limit_col=df["detection_limit"])`.
  Parse with `cairn.checks.parse_censored(series)` into value / censored / limit.
- Profile limits by year and by laboratory. A limit that fell over time creates an
  apparent decline; one that rose hides a real one.
- Do not substitute zero, the limit, or half the limit as the main estimate.
- Quantiles above the highest limit are identifiable directly (sort with censored values
  at their limits; a median is fine if more than half the data are detects above the
  limit). Means are not identifiable without a model: give interval bounds (all censored
  at 0 vs all at the limit), or a Kaplan-Meier / regression-on-order-statistics estimate
  with the method named, or state that the mean is not identifiable.
- Share above a threshold is identifiable if every limit is below the threshold.
- Record what you did: `record("arsenic.n_censored", n)` and `record("arsenic.method",
  "KM")`, and say it next to the number in the report.
