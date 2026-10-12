# Pre-registration

## Question
Purchase conversion by variant (A/B) of the checkout A/B test, all exposed users.

## Primary quantity
Share of exposed users with >=1 purchase event, per variant; difference B-A in percentage points.

## Unit of analysis
The user (exposures table is one row per user). Multiple purchases collapse to one indicator.

## Population and comparability
Denominator: all rows of the exposures table, including users with no events (absent from the events table). No exclusions.
Purchases counted at any time (no timestamp window defined in the dictionary).

## Handling of missing and censored values
None expected; no censored measurements.

## Decision rule
Report point estimates; abstain if users are duplicated or appear in both variants.

## Confirmatory vs exploratory
The above is confirmatory; anything else is exploratory.
