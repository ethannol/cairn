import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import Grade, close, grader_main  # noqa: E402


def grade(answer: dict, expected: dict) -> dict:
    g, gold = Grade(), expected["gold_answer"]
    g.require(
        close(answer.get("grand_total"), gold["grand_total"], rel=1e-3),
        f"grand_total {answer.get('grand_total')} != {gold['grand_total']}",
    )
    g.require(
        answer.get("n_orders") == gold["n_orders"],
        f"n_orders {answer.get('n_orders')} != {gold['n_orders']}",
    )
    for field in ("total_by_region", "total_by_current_segment"):
        got = answer.get(field) or {}
        for k, v in gold[field].items():
            g.require(close(got.get(k), v, rel=1e-3), f"{field}[{k}] {got.get(k)} != {v}")
    return g.result()


grader_main(grade)
