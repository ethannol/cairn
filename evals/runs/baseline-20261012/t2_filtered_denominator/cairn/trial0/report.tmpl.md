# Checkout A/B test: purchase conversion

## Question

Share of exposed users with at least one purchase, by variant, and the B minus A difference.

## Data and comparability

One exposure row is one user ({{n.total}} users; unique ids). The denominator is every exposed user, including those with no events. No exclusions. Purchases are counted at any time; the data dictionary defines no window.

## Method

Conversion = users with a purchase event / exposed users, per variant.

## Result

Variant A: {{conv.A:.4f}} (n = {{n.A}}). Variant B: {{conv.B:.4f}} (n = {{n.B}}). Difference B - A: {{diff_pp:.2f}} pp.

## Caveats next to the claims they affect

The interval below is exploratory (not pre-registered): a Wald interval for the difference, treating users as independent, runs from {{diff_ci_low_pp:.2f}} to {{diff_ci_high_pp:.2f}} pp. No randomisation checks were run.

## Decision log

See `docs/decisions.md`.
