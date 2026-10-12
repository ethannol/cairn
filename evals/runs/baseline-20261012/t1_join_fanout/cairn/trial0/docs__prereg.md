# Pre-registration

## Question
Total 2024 order revenue by customer region, by customer current segment, and overall.

## Primary quantity
Sum of orders.amount (USD): grand total, per region, per current segment.

## Unit of analysis
The order (one row per order_id); customers are a lookup dimension. Segment history is collapsed to one row per customer (latest valid_from) before joining, so orders are not duplicated.

## Population and comparability
All 5000 orders. Join checks m:1 to customers and to current segments; totals by group must equal the grand total.

## Handling of missing and censored values
No nulls found in profiling; amounts are plain numbers, no censoring.

## Decision rule
If group totals do not reconcile with the grand total, or orders lose customers, investigate before reporting.

## Confirmatory vs exploratory
The three totals and n_orders are confirmatory; anything else is exploratory.
