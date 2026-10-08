# 2. Every reported number comes from a ledger written by scripts

Date: 2026-10-07. Status: accepted.

## Context

Practitioner reports (Tian Pan, ZURB, Hex) describe agents writing summaries with numbers
that were never computed, or computed once and then edited. 26% of failed agent runs in
the Terminal-Bench anatomy fabricate success. Anthropic's xlsx skill rule "use formulas,
never hardcoded results" is the same idea for spreadsheets.

## Decision

`cairn.record(key, value, ...)` writes `artifacts/numbers.json` with the producing
script and timestamp. The report is a template with `{{key}}` placeholders; `cairn render`
substitutes; `cairn verify` fails on unresolved keys, warns on bare numeric literals in
prose, and re-executes the pipeline into a scratch ledger to confirm every value is
reproduced within tolerance. Answers in `questions.json` must cite ledger keys.

## Consequences

- Hand-editing a result anywhere (ledger, report, questions) is caught by the rerun.
- Costs a full re-execution on verify; `stop_hook_rerun = false` keeps the Stop hook
  fast and leaves the rerun to an explicit `cairn verify`.
- Rejected: parsing numbers out of stdout; trusting the report prose; an LLM check that
  "numbers look consistent".
