# cairn design

Working notes for the harness. The research behind every choice is in
[research/research-report.md](research/research-report.md); the decisions are in
[decisions/](decisions/).

## Thesis

A data analysis agent does not fail by crashing. It fails by producing a clean-running,
plausible, wrong number: a join that fans out, a denominator from a filtered table, a
feature recorded after the outcome, a non-detect treated as a measurement, a conclusion
steered by how the question was framed. Expert review misses most of these (the
forking-paths studies put the pass rate for steered analyses at 78 to 86 percent), and
LLM judges agree with humans only moderately on statistical quality.

So the harness does not try to make the agent smarter. It gives one Claude Code session
autonomy and surrounds it with sensors it cannot edit:

| Sensor | What it enforces | Where |
|---|---|---|
| Protected paths | raw data, pre-registration, harness config are read-only | PreToolUse hook |
| Profile gate | row grain, candidate keys, nulls, censoring markers visible before any join | `cairn profile`, skill step 1 |
| Pre-registration freeze | question, quantity, unit, population, censoring method, decision rule fixed before results; hash checked | `cairn freeze`, `verify` stage 1-2 |
| Question list | agent may only set status / answer_keys / notes; cannot reword or drop a question | snapshot diff, PostToolUse + verify |
| Data checks | join cardinality and match rate, row recounts, split overlap, time order, target proxies, censoring detection, all appended to `checks.jsonl` | `cairn.checks`, verify stage 5 |
| Script lint | merge without validate, naive fills, shuffled time splits, fit on full data, literal percentages in prints | PostToolUse hook, verify stage 4 |
| Numbers ledger | every reported figure is `record()`ed by a script with provenance; report uses `{{key}}`; bare numbers flagged | `cairn.numbers`, verify stage 6 |
| Clean re-execution | scripts rerun from an empty ledger must reproduce every value | verify stage 7 |
| Stop gate | agent cannot end the turn while verify fails (bounded attempts) | Stop hook |
| Fresh reviewer | forked context, read-only, correctness-only checklist | `/review-analysis` skill |

Everything in the left column is deterministic code. The only LLM-judged step is the
reviewer, and it is advisory.

## What the agent experiences

1. `SessionStart` hook prints: frozen or not, open questions, ledger size, last verify.
2. CLAUDE.md (under 60 lines) states the non-negotiables and points at `/analysis-workflow`.
3. The skill lays out the order: inspect, establish comparability, pre-register and freeze,
   compute in scripts with checks, report from the ledger, verify, review.
4. Each file write is linted; each attempt to touch raw data or the plan is denied with a
   reason; each attempt to stop is met with the verify summary until it passes.

## Non-goals (v0.1)

- No search over candidate solutions, no multi-agent planner/critic. The MLE-bench
  ablations show these add little once the agent has execution feedback.
- No notebook kernel. Scripts under `uv run` are the unit of reproducibility; marimo is a
  possible later option for exploration.
- No hidden holdout for ordinary analysis. It is in the research as a differentiator but
  changes how a human works with the project. Deferred to an ADR.
- No LLM judge in `verify`.

## Evaluation

`evals/` holds trap tasks with deterministic graders, each targeting a documented failure
mode that published benchmarks do not measure. The harness is tested by running the same
task under two conditions, bare Claude Code and Claude Code plus cairn, several trials
each, and reporting pass rate per failure mode with cost per trial. See
[../evals/README.md](../evals/README.md).

## Roadmap

- v0.1: sensors, template, skills, hooks, trap suite with six tasks, eval runner.
- v0.2: run the suite, publish per-failure-mode results in the README; pandera contracts
  between steps; Quarto report rendering.
- v0.3: hidden-holdout protocol as an opt-in; censored-data estimators (KM/ROS helpers);
  port groundwater-audit's Condition B onto cairn and compare.
