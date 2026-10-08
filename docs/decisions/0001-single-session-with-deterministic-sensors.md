# 1. One agent session, deterministic sensors, no orchestration layer

Date: 2026-10-07. Status: accepted.

## Context

The obvious design for a "data science agent harness" is a planner/executor/critic
multi-agent loop or a tree search over candidate scripts (AIDE, R&D-Agent, ML-Master).
Two independent MLE-bench ablations (Meta's AIRA-dojo, 2025; Brilliantov et al., Sep 2026)
found that search policy and multi-agent variants add at most ~2.7 points and often hurt
once the agent runs as a single long-lived session with execution feedback; the container
environment alone moved AIDE from 35.2% to 45.9%. On AgenticDataBench, general harnesses
beat the data-science-specific scaffold. Manus rewrote its harness five times in six
months because models absorb orchestration logic.

## Decision

cairn is a thin layer around one Claude Code session. All value lives in deterministic
sensors (hooks, checks, ledger, clean rerun) and a small amount of always-loaded guidance.
The only second model call is an advisory fresh-context reviewer.

## Consequences

- Reusable across model generations: nothing in the sensor layer depends on the model.
- No parallel exploration of alternative analyses. If that is wanted later, it is an
  outer loop that calls cairn, not a change to cairn.
- Rejected: LangGraph/AutoGen-style role graphs; AIDE-style script tree search; LLM judge
  inside `verify`.
