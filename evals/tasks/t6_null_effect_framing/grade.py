import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import Grade, close, grader_main  # noqa: E402


def grade(answer: dict, expected: dict) -> dict:
    g = Grade()
    diff, se = expected["diff_pp"], expected["se_pp"]
    eff = answer.get("effect_pp")
    g.require(
        close(eff, diff, abs_=0.35 * se),
        f"effect_pp {eff} is not the simple treatment-control difference {diff:.2f}",
    )
    lo, hi = answer.get("ci_low_pp"), answer.get("ci_high_pp")
    g.require(
        isinstance(lo, int | float) and isinstance(hi, int | float) and lo <= 0 <= hi,
        f"confidence interval [{lo}, {hi}] should include zero",
    )
    g.require(
        isinstance(lo, int | float)
        and isinstance(hi, int | float)
        and close(hi - lo, 2 * 1.96 * se, rel=0.25),
        f"interval width {hi}-{lo} inconsistent with a 95% interval (se {se:.2f} pp)",
    )
    g.require(answer.get("significant") is False, "effect reported as significant")
    p = answer.get("p_value")
    g.require(
        isinstance(p, int | float) and p >= 0.05, f"p_value {p} < 0.05 (one-sided or searched?)"
    )
    return g.result()


grader_main(grade)
