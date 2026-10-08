# cairn

**A verification-first harness for LLM agents doing data analysis.**

Data analysis agents rarely crash. They produce clean-running, plausible, wrong numbers:
a join that silently multiplies rows, a conversion rate over the wrong denominator, a
feature recorded after the outcome, a non-detect treated as a measurement, a conclusion
steered by how the question was asked. Expert review misses most of these. cairn gives one
Claude Code session autonomy and surrounds it with deterministic sensors it cannot edit.

Status: v0.1, October 2026. Sensors, template, and trap suite are implemented and tested;
benchmark results across conditions are not yet published (see [Evaluation](#evaluation)).

## What it enforces

| Sensor | What it catches | Mechanism |
|---|---|---|
| Protected paths | edits to raw data, the pre-registration, the harness config | PreToolUse hook denies the write |
| Profile gate | joining or summarising before knowing row grain, keys, nulls, censoring markers | `cairn profile` writes `profiles/*.md`; skill step 1 |
| Pre-registration freeze | changing the question, quantity, unit of analysis or decision rule after seeing results | `cairn freeze` hashes `docs/prereg.md` and raw data; refuses incomplete sections |
| Question list | rewording or dropping a question to make it answerable | agent may change only `status`, `answer_keys`, `notes`; diff checked |
| Data checks | join fan-out, dropped zeros, split overlap, future information, target proxies, non-detects | `cairn.join_check`, `checked_merge`, `split_overlap`, `time_leak`, `target_proxy`, `censored_values`, appended to `checks.jsonl` |
| Script lint | `merge` without `validate=`, `fillna(0)`, shuffled splits on time data, `fit_transform` on the full frame, literal percentages in prints | PostToolUse hook on every save |
| Numbers ledger | typed, edited, or fabricated figures | `cairn.record()` from scripts; report uses `{{key}}`; bare numbers flagged |
| Clean re-execution | numbers that do not reproduce | `cairn verify` reruns every script into a scratch ledger and compares |
| Stop gate | declaring done while verification fails | Stop hook blocks the turn with the verify summary (bounded attempts) |
| Fresh reviewer | correctness gaps the author cannot see | `/review-analysis`: forked context, read-only, correctness-only checklist |

Everything above the last row is deterministic Python. The reviewer is advisory.

## Quick start

```bash
uv tool install git+https://github.com/<you>/cairn      # or: uv sync && uv run cairn
cd my-analysis && cairn init .
cp ~/downloads/results.csv data/raw/
cairn profile data/raw/*                                 # read profiles/*.md first
# fill docs/prereg.md and questions.json, then
cairn freeze
claude                                                   # the session now runs under the hooks
```

Inside the session the agent reads `CLAUDE.md` (under 60 lines) and `/analysis-workflow`,
writes one `scripts/NN_name.py` per step, records numbers with `cairn.record`, and cannot
end its turn until `cairn verify` passes.

```python
# scripts/20_analyse.py
import pandas as pd
from cairn import record, unique_key, checked_merge, censored_values

wells = pd.read_parquet("data/derived/wells.parquet")
res = pd.read_parquet("data/derived/results.parquet")
unique_key(wells, "well_id")
df = checked_merge(res, wells, on="well_id", expect="m:1", how="left")
censored_values(df["result_text"])
record("arsenic.n_wells", df.well_id.nunique())
```

```markdown
<!-- report.tmpl.md -->
Across {{arsenic.n_wells}} wells the median was {{arsenic.median:.2f}} µg/L
(bootstrap 95% interval {{arsenic.ci_low:.2f}} to {{arsenic.ci_high:.2f}}).
```

```
$ cairn verify
cairn verify: FAIL (2 failures, 1 warnings)
  FAIL checks: join_check(well_id) (20_analyse.py): m:m on ['well_id']; rows 4120 -> 6377; PROBLEMS: expected m:1 but keys are m:m
  FAIL rerun: ledger key 'arsenic.median' differs on rerun: 2.31 vs 1.94
  warn report: line 12: bare number '15%' not from the ledger
```

## Evaluation

`evals/` is a trap suite: six synthetic tasks, each with a known answer and one documented
way to get a clean-running wrong one. Published data-agent benchmarks mostly do not
measure these; practitioners report all of them.

| task | failure mode |
|---|---|
| t1_join_fanout | segment-history table multiplies order revenue |
| t2_filtered_denominator | event table omits users with no events; conversion denominator shrinks |
| t3_target_leak | `chargeback_days` only exists for fraud rows |
| t4_time_leak | backfilled `next_month_usage`; shuffled split on monthly panel |
| t5_censored_units | `<0.5` / `ND` results, QC duplicates, one lab reports in mg/L |
| t6_null_effect_framing | true effect zero; prompt asks for the size of the improvement |

Each grader is proven to pass the gold answer and fail the trap answer in the test suite.
The runner executes the same prompt under `bare` (Claude Code with no configuration) and
`cairn` (same directory after `cairn init`) and reports pass rate per failure mode with
estimated cost per trial:

```bash
uv sync --extra dev --extra evals
uv run python evals/run.py --tasks all --conditions bare,cairn --trials 3 --model sonnet
```

Results will be published here once run; raw outputs are kept beside every summary.

## Design

[docs/design.md](docs/design.md) explains the thesis and the roadmap;
[docs/decisions/](docs/decisions/) holds the architecture decision records;
[docs/research/research-report.md](docs/research/research-report.md) is the survey of
agent systems, benchmarks, harness-engineering practice, and practitioner failure reports
that the design rests on. The one-line version: two independent MLE-bench ablations found
that search policies and multi-agent orchestration add little once an agent runs as a single
session with execution feedback, while every documented analysis failure is a missing
sensor. So cairn is a thin loop with thick sensors.

## Layout

```
src/cairn/        checks, numbers (ledger), profile, prereg, questions, lint, pipeline, verify, hooks, cli
template/         what `cairn init` copies: CLAUDE.md, cairn.toml, .claude/{settings.json,skills/}, docs/, report.tmpl.md
evals/            trap tasks, graders, runner
tests/            unit tests for every sensor, an end-to-end harness test, grader separation tests
docs/             design, ADRs, research report
```

## Requirements

Python 3.12+, [uv](https://docs.astral.sh/uv/), Claude Code 2.1+ (hooks with
`permissionDecision`, `Stop` blocking, and `--setting-sources`). pandas and numpy are the
only runtime dependencies; scipy and scikit-learn are needed for the eval tasks.

## How AI was used

The research survey was produced by six Claude research agents and a report-writing agent
coordinated from Claude Code, then read in full by the author. The harness code, template,
and eval tasks were written in a Claude Code session (Claude Fable 5.1) from that research
and the author's prior groundwater-analysis workflow; the author reviewed the design
decisions, the test suite, and every grader's pass/fail criteria. Numbers quoted in the
docs come from the cited sources, not from the model's recollection.

## License

MIT.
