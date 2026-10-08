# Analysis project (cairn harness)

This project is run with the cairn harness. The harness, not this file, enforces
the rules: hooks deny writes to protected paths, lint scripts on save, and run
`cairn verify` before you may finish. Read `/analysis-workflow` before computing.

## Non-negotiables

- `data/raw/` is immutable. Derived tables go in `data/derived/`, outputs in `artifacts/`.
- Profile before you join or summarise: `cairn profile data/raw/*` and read `profiles/*.md`.
  Say what one row represents before you count anything.
- Fill `docs/prereg.md` and `questions.json`, then run `cairn freeze` before computing results.
  After freezing, label anything outside the plan as exploratory.
- Every number in the report comes from code: `from cairn import record; record("key", value, n=...)`
  in a `scripts/NN_name.py` step, referenced as `{{key}}` in `report.tmpl.md`.
  Never type a result into the report, the ledger, or `questions.json`.
- Before any merge, run `cairn.join_check(...)` or use `cairn.checked_merge(...)`.
  Before any split, run `cairn.split_overlap` and `cairn.time_leak`.
  Before summarising a measurement column, run `cairn.censored_values`.
- Report uncertainty the sampling structure supports. Repeated measures on one unit are not
  independent. Do not report precision the data cannot carry.
- A justified abstention is a valid answer: set the question's status to `abstained` with the
  reason in `notes`.

## Commands

- `cairn status` / `cairn ledger` — what is frozen, recorded, open
- `cairn run` — execute `scripts/NN_*.py` in order and rebuild the ledger
- `cairn verify` — all sensors, including a clean re-execution
- `cairn render` — write `report.md` from `report.tmpl.md` and the ledger

## Layout

```
data/raw/        immutable inputs (+ data dictionary in docs/)
data/derived/    cleaned, comparable tables written by scripts
scripts/         00_profile.py, 10_prepare.py, 20_analyse.py, ... one step each
artifacts/       numbers.json (ledger), checks.jsonl, tables, figures
profiles/        cairn profile output
docs/            prereg.md (frozen), data_dictionary.md, decisions.md (append-only log)
report.tmpl.md   prose with {{ledger.keys}}; report.md is rendered, never edited
```
