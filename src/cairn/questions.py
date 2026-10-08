"""The question list: what the analysis must answer.

`questions.json` is written by the human (or at init) and snapshotted at
freeze time. The agent may only change `status`, `answer_keys` and `notes` on
existing questions. It may not add, remove or reword questions, which is the
analysis analogue of Anthropic's "the agent may only change the passes field".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cairn.config import Config

AGENT_WRITABLE = {"status", "answer_keys", "notes"}
STATUSES = {"open", "answered", "abstained", "exploratory"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.is_file() else {"questions": []}


def diff_problems(base: dict[str, Any], current: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    bq = {q["id"]: q for q in base.get("questions", [])}
    cq = {q["id"]: q for q in current.get("questions", [])}
    for qid in bq.keys() - cq.keys():
        problems.append(f"question '{qid}' was removed")
    for qid in cq.keys() - bq.keys():
        problems.append(f"question '{qid}' was added after freeze")
    for qid in bq.keys() & cq.keys():
        for field, val in bq[qid].items():
            if field in AGENT_WRITABLE:
                continue
            if cq[qid].get(field) != val:
                problems.append(f"question '{qid}': field '{field}' was changed")
        for field in cq[qid].keys() - bq[qid].keys():
            if field not in AGENT_WRITABLE:
                problems.append(f"question '{qid}': unexpected new field '{field}'")
        status = cq[qid].get("status", "open")
        if status not in STATUSES:
            problems.append(f"question '{qid}': status {status!r} not in {sorted(STATUSES)}")
    return problems


def answer_problems(current: dict[str, Any], ledger: dict[str, Any]) -> list[str]:
    """Every answered question must point at ledger keys that exist."""
    problems: list[str] = []
    for q in current.get("questions", []):
        status = q.get("status", "open")
        keys = q.get("answer_keys") or []
        if status == "answered" and not keys:
            problems.append(f"question '{q['id']}' is answered but lists no answer_keys")
        for k in keys:
            if k not in ledger:
                problems.append(f"question '{q['id']}' cites ledger key '{k}' which does not exist")
        if status == "abstained" and not (q.get("notes") or "").strip():
            problems.append(f"question '{q['id']}' is abstained without a reason in notes")
    return problems


def check(cfg: Config, ledger: dict[str, Any]) -> list[str]:
    base_path = cfg.state_dir / "questions.base.json"
    current = load(cfg.questions_path)
    problems: list[str] = []
    if base_path.is_file():
        problems += diff_problems(load(base_path), current)
    problems += answer_problems(current, ledger)
    return problems


def open_questions(cfg: Config) -> list[dict[str, Any]]:
    return [
        q
        for q in load(cfg.questions_path).get("questions", [])
        if q.get("status", "open") == "open"
    ]
