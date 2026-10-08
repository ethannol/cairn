import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import Grade, close, grader_main  # noqa: E402


def grade(answer: dict, expected: dict) -> dict:
    g, gold = Grade(), expected["gold_answer"]
    for v in ("A", "B"):
        g.require(
            close(answer.get(f"conversion_{v}"), gold[f"conversion_{v}"], abs_=1e-3),
            f"conversion_{v} {answer.get(f'conversion_{v}')} != {gold[f'conversion_{v}']:.4f}",
        )
        g.require(
            answer.get(f"n_{v}") == gold[f"n_{v}"],
            f"n_{v} {answer.get(f'n_{v}')} != {gold[f'n_{v}']} (denominator must be exposed users)",
        )
    g.require(
        close(answer.get("diff_pp"), gold["diff_pp"], abs_=0.1),
        f"diff_pp {answer.get('diff_pp')} != {gold['diff_pp']:.2f}",
    )
    return g.result()


grader_main(grade)
