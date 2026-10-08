import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import Grade, close, grader_main  # noqa: E402

NAMED_METHODS = (
    "kaplan",
    "km",
    "ros",
    "regression on order",
    "mle",
    "maximum likelihood",
    "interval",
    "bound",
    "tobit",
    "censored",
)


def grade(answer: dict, expected: dict) -> dict:
    g, gold = Grade(), expected["gold_answer"]
    g.require(
        answer.get("n_wells") == gold["n_wells"],
        f"n_wells {answer.get('n_wells')} != {gold['n_wells']}",
    )
    g.require(
        answer.get("n_samples") == gold["n_samples"],
        f"n_samples {answer.get('n_samples')} != {gold['n_samples']} (QC duplicates?)",
    )
    g.require(
        answer.get("n_censored") == gold["n_censored"],
        f"n_censored {answer.get('n_censored')} != {gold['n_censored']}",
    )
    g.require(
        close(answer.get("share_above_1"), gold["share_above_1"], abs_=0.005),
        f"share_above_1 {answer.get('share_above_1')} != {gold['share_above_1']:.4f}",
    )
    lo, hi = expected["median_bounds"]
    med = answer.get("median_ugL")
    g.require(
        isinstance(med, int | float) and lo * 0.98 <= med <= hi * 1.02,
        f"median_ugL {med} outside identifiable range [{lo:.3f}, {hi:.3f}]",
    )
    ident = answer.get("mean_identifiable")
    mean, method = answer.get("mean_ugL"), str(answer.get("mean_method") or "").lower()
    if ident is False or mean is None:
        pass  # declaring the mean non-identifiable is correct
    else:
        g.require(
            any(k in method for k in NAMED_METHODS),
            f"mean reported ({mean}) without a named censored method: {method!r}",
        )
        blo, bhi = expected["mean_bounds_ugL"]
        g.require(
            isinstance(mean, int | float) and blo * 0.95 <= mean <= bhi * 1.05,
            f"mean_ugL {mean} outside the bounds [{blo:.3f}, {bhi:.3f}] implied by censoring",
        )
        g.require("substitut" not in method, "substitution used as the main mean method")
    return g.result()


grader_main(grade)
