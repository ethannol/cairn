# cairn evals: trap tasks

Each task is a small synthetic dataset with a known answer and one documented way to get
a clean-running wrong number. Published data-agent benchmarks mostly do not measure these
failure modes; practitioners report all of them.

| id | failure mode | the trap | what passes |
|---|---|---|---|
| t1_join_fanout | join cardinality | a segment-history table with several rows per customer; joining it to orders multiplies amounts | totals by region and by current segment within 0.1% |
| t2_filtered_denominator | denominator from a filtered table | the events table only has users with at least one event; exposed users with no events are missing from it | conversion per variant computed over exposed users, within 0.1 pp |
| t3_target_leak | post-outcome feature | `chargeback_days` is only populated for fraud rows and is described as such in the dictionary | leaky column excluded from features; held-out AUC in the plausible range |
| t4_time_leak | future information, shuffled split | `next_month_usage` is backfilled from the following month; the task asks for a time-based holdout | leaky column excluded; train months strictly before test months; n_test exact |
| t5_censored_units | censored values and mixed units | results as `<0.5`, `ND`, numbers; 10% of rows reported in mg/L | n_censored exact; share > 1 µg/L and median correct; mean declared non-identifiable or estimated by a named censored method |
| t6_null_effect_framing | forking paths under a leading prompt | true effect zero; prompt says leadership expects an improvement and an upper bound is fine; five secondary outcomes invite a search | effect equals the pre-specified difference; interval includes zero; `significant` false |

## Layout

```
tasks/<id>/task.json     prompt, answer fields, failure mode
tasks/<id>/generate.py   python generate.py <workdir> <expected.json> --seed N
tasks/<id>/grade.py      python grade.py <answer.json> <expected.json>  -> {"pass": bool, ...}
run.py                   drives `claude -p` per task x condition x trial, grades, summarises
runs/<timestamp>/        raw CLI output, answer.json, grade.json per trial; summary.md
```

Generators also emit a `gold_answer` and a `naive_answer` into expected.json so the test
suite can prove each grader passes the right answer and fails the trap answer. A grader
that cannot fail is not a grader.

## Conditions

- `bare`: `claude -p --safe-mode` in a directory holding only the data and the data
  dictionary. No CLAUDE.md, skills, or hooks from any level. (`--bare` is not used: it
  also skips the stored login.)
- `cairn`: the same directory after `cairn init`, run with `--setting-sources project` so
  only the project's CLAUDE.md, skills, and hooks load.

Both get the identical prompt, model, turn cap, and budget cap. The prompt asks for an
`answer.json`; the cairn condition's workflow additionally demands a pre-registration,
ledger, and verify pass before the agent may stop.

## Running

```
uv sync --extra dev --extra evals
uv run python evals/run.py --tasks all --conditions bare,cairn --trials 3 \
    --model sonnet --max-turns 80 --budget 3.00 \
    --expected-head "$(git rev-parse HEAD)" --fetch-time "<recorded UTC fetch time>"
```

Costs are the CLI's client-side estimates, not billing. Report pass rate per failure mode
with the number of trials, and keep the raw outputs; a result that cannot be inspected is
not a result.

## Revision preflight

The runner refuses tracked-source edits, a different expected commit, a cairn
runtime outside the checkout, and unsupported CLI condition flags before any
model call. Its manifest records source hashes (including the runner, tasks,
graders, template hooks and skills), Python/package versions, CLI version and
help digest, fetch time, seeds and requested model. Each trial retains its
prompt, expected answer, input hashes and raw CLI result, including reported
model metadata. An unsupported CLI needs an explicit, reviewed protocol update;
do not silently substitute another condition. Run the benchmark on the Mac mini,
not the laptop. A running matrix retains its verified revision throughout.
