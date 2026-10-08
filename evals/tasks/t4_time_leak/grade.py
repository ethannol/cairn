import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import Grade, grader_main  # noqa: E402


def grade(answer: dict, expected: dict) -> dict:
    g = Grade()
    feats = [str(f).lower() for f in (answer.get("features") or [])]
    for leak in expected["leaky"]:
        g.require(not any(leak in f for f in feats), f"future-information feature used: {leak}")
    te, tr = str(answer.get("test_start", ""))[:7], str(answer.get("train_end", ""))[:7]
    g.require(te == expected["test_months"][0], f"test_start {te} != {expected['test_months'][0]}")
    g.require(bool(tr) and tr < te, f"train_end {tr} is not before test_start {te}")
    g.require(
        answer.get("n_test") == expected["n_test"],
        f"n_test {answer.get('n_test')} != {expected['n_test']}",
    )
    auc = answer.get("test_auc")
    g.require(
        isinstance(auc, int | float) and 0.55 <= auc <= 0.9,
        f"test_auc {auc} outside the plausible range [0.55, 0.9]",
    )
    return g.result()


grader_main(grade)
