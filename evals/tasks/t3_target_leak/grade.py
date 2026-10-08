import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import Grade, close, grader_main  # noqa: E402


def grade(answer: dict, expected: dict) -> dict:
    g = Grade()
    feats = [str(f).lower() for f in (answer.get("features") or [])]
    for leak in expected["leaky"]:
        g.require(not any(leak in f for f in feats), f"leaky feature used: {leak}")
    g.require(feats != [], "no features listed")
    auc = answer.get("auc")
    g.require(
        isinstance(auc, int | float) and 0.6 <= auc <= 0.93,
        f"auc {auc} outside the plausible range [0.6, 0.93] for a leak-free model",
    )
    g.require(
        close(answer.get("fraud_rate"), expected["fraud_rate"], abs_=1e-3),
        f"fraud_rate {answer.get('fraud_rate')} != {expected['fraud_rate']:.4f}",
    )
    g.require(bool(str(answer.get("split", "")).strip()), "split not described")
    return g.result()


grader_main(grade)
