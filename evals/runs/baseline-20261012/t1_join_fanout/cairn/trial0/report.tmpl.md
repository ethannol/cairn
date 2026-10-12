# 2024 order revenue by region and current segment

## Question

Total 2024 order revenue overall, by customer region, and by customer current segment.

## Data and comparability

One row in orders is one order. No orders were excluded. Each customer's current segment is the segment row with the latest valid_from; orders were joined to customers and to current segments many-to-one, with row counts unchanged.

## Method

Sum of order amount, grouped by region and by current segment. The unit of analysis is the order; no sampling uncertainty is reported because these are totals over all recorded orders, not estimates.

## Result

Grand total: {{grand_total:.2f}} USD.

Region: east {{region.east:.2f}}, north {{region.north:.2f}}, south {{region.south:.2f}}, west {{region.west:.2f}}.

Current segment: basic {{segment.basic:.2f}}, plus {{segment.plus:.2f}}, premium {{segment.premium:.2f}}.

## Caveats next to the claims they affect

Segment totals attribute all of a customer's 2024 orders to their latest segment, even if they were in another segment when ordering.

## Exploratory findings (not pre-registered)

None.

## Decision log

See `docs/decisions.md`.
