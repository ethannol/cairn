"""cairn: a verification-first harness for LLM agents doing data analysis.

The agent gets autonomy inside one session; the harness owns the sensors:
protected inputs, a frozen pre-registration, a numbers ledger that every
reported figure must come from, deterministic data checks, and a clean
re-execution before the agent may declare the work done.
"""

from cairn.checks import (
    CheckResult,
    censored_values,
    checked_merge,
    denominator,
    join_check,
    recount,
    split_overlap,
    time_leak,
    unique_key,
)
from cairn.numbers import load_ledger, record, render

__all__ = [
    "CheckResult",
    "censored_values",
    "checked_merge",
    "denominator",
    "join_check",
    "load_ledger",
    "record",
    "recount",
    "render",
    "split_overlap",
    "time_leak",
    "unique_key",
]

__version__ = "0.1.0"
