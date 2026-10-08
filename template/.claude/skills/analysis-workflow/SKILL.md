---
name: analysis-workflow
description: Required order of work for any data analysis in a cairn project - profile, establish comparability, pre-register, compute in scripts with checks, report from the ledger, verify. Use before computing any result, and again before writing the report.
---

# Analysis workflow

Work in this order. Each step leaves evidence on disk that `cairn verify` checks.

## 1. Inspect before computing

1. Read `docs/data_dictionary.md` and any source documentation under `docs/`. If the
   dictionary is empty, write it from the source docs before anything else. Do not invent
   column meanings, units, or file contents.
2. Run `cairn profile data/raw/*` and read every `profiles/*.md`. For each table write down,
   in `docs/decisions.md`: what one row represents, the candidate key, null rates on the
   fields you will rely on, and any censoring markers or mixed numeric/text columns.
3. Identify which rows are the population and which are quality-control, duplicates,
   test records, or out of scope. Say what you do with each class.

## 2. Establish comparability

4. Group measurements by everything that could make them a different quantity: definition,
   unit, fraction, method, version, currency, time zone. Treat groups as different until
   shown equivalent in this dataset. Convert units with an explicit written factor.
5. For every join: `cairn.join_check(left, right, on=..., expect="m:1")` first, then
   `cairn.checked_merge(...)`. Report rows before and after. Read [joins.md](joins.md).
6. For every rate: state the denominator population explicitly with
   `cairn.denominator(numerator, population, "metric", population_desc=...)`. A filtered
   table is not the population. Zero-event units belong in the denominator.

## 3. Pre-register, then freeze

7. Fill every section of `docs/prereg.md` and the real questions in `questions.json`.
   Decide the decision rule and what would make you abstain before seeing results.
8. Run `cairn freeze`. From here, changes to the plan are exploratory and labelled.

## 4. Compute in scripts, with checks

9. One step per `scripts/NN_name.py`, re-runnable from clean. Scripts read `data/raw/`
   or `data/derived/`, write `data/derived/` or `artifacts/`, and record every reportable
   number with `cairn.record("dotted.key", value, unit=..., n=...)`.
10. Censored or non-detect values: `cairn.censored_values(series)` then a censored method
    (interval bounds, Kaplan-Meier/ROS, or a statement that the quantity is not
    identifiable). Substitution is a labelled sensitivity check only. Read [censored.md](censored.md).
11. Any model or held-out comparison: split first, fit preprocessing on train only, run
    `cairn.split_overlap` and `cairn.time_leak`, and `cairn.target_proxy` on the features.
    Select on validation, report on the untouched holdout once. Read [leakage.md](leakage.md).
12. Uncertainty must match the sampling structure: resample at the unit level (wells,
    customers), not the row level. Repeated measures within a unit are not independent.
13. Run `cairn run`, then `cairn verify --quick`. Fix failures before continuing.

## 5. Report from the ledger

14. Write `report.tmpl.md` with `{{key}}` placeholders for every number. No typed numbers
    in prose. Put each caveat next to the claim it affects. Read [reporting.md](reporting.md).
15. Mark each question in `questions.json` as `answered` (listing the `answer_keys`),
    `abstained` (with the reason in `notes`), or `exploratory`.
16. Run `cairn verify` (with the clean rerun) and `cairn render`. Then invoke
    `/review-analysis` for a fresh-context review, and address what it finds.

## When to abstain

If metadata is missing or inconsistent such that the comparison is not defensible, say so
and stop at the strongest claim the data support. That is a valid, complete answer.
