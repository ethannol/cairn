# 3. Pre-register and freeze before computing

Date: 2026-10-07. Status: accepted.

## Context

Belief priming alone reproduces 72% of the human ideological gap in agent effect estimates
(Miao et al., 2026); "upper bound" framing drives frontier models into specification
search on null data (Asher et al.). Pre-registration blocked ~73% of prompt-hack transfer
in Thomas et al. (2026). No practitioner harness implements it.

## Decision

`docs/prereg.md` has seven required sections (question, primary quantity, unit of
analysis, population/comparability, censored handling, decision rule,
confirmatory/exploratory). `cairn freeze` refuses incomplete sections, hashes the file
and raw data into `.cairn/frozen.json`, and snapshots the question list. The file is then
protected; any later work outside the plan is reported as exploratory.

## Consequences

- Forces the analyst (human or agent) to decide the decision rule before seeing results.
- Open question for a later ADR: should the gate block exploratory work or only label it?
  v0.1 labels; the Stop hook does not block on exploratory sections.
