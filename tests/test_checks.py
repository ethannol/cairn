import numpy as np
import pandas as pd
import pytest

from cairn import checks


@pytest.fixture(autouse=True)
def _checks_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CAIRN_CHECKS", str(tmp_path / "checks.jsonl"))


def test_unique_key_detects_duplicates():
    df = pd.DataFrame({"id": [1, 2, 2, 3]})
    r = checks.unique_key(df, "id", quiet=True)
    assert not r.passed
    assert r.details["duplicated_rows"] == 2
    assert checks.unique_key(df.drop_duplicates("id"), "id", quiet=True).passed


def test_join_check_flags_fanout_and_cardinality():
    orders = pd.DataFrame({"customer_id": [1, 1, 2, 3], "amount": [10, 20, 30, 40]})
    attrs = pd.DataFrame({"customer_id": [1, 1, 2, 2, 3], "segment": list("ababa")})
    r = checks.join_check(orders, attrs, on="customer_id", expect="m:1", quiet=True)
    assert not r.passed
    assert r.details["observed"] == "m:m"
    assert r.details["fanout"] == pytest.approx(7 / 4)
    assert "multiply" in r.message


def test_join_check_passes_clean_m1_and_reports_match_rate():
    orders = pd.DataFrame({"customer_id": [1, 1, 2, 9], "amount": [10, 20, 30, 40]})
    cust = pd.DataFrame({"customer_id": [1, 2, 3], "region": list("xyz")})
    r = checks.join_check(orders, cust, on="customer_id", expect="m:1", quiet=True)
    assert r.passed
    assert r.details["row_match_rate"] == pytest.approx(0.75)
    assert r.details["unmatched_examples"] == [{"customer_id": 9}]
    r2 = checks.join_check(
        orders, cust, on="customer_id", expect="m:1", min_match_rate=0.9, quiet=True
    )
    assert not r2.passed


def test_checked_merge_refuses_fanout_and_sets_validate():
    orders = pd.DataFrame({"customer_id": [1, 2], "amount": [10, 20]})
    attrs = pd.DataFrame({"customer_id": [1, 1], "segment": ["a", "b"]})
    with pytest.raises(ValueError, match="refused"):
        checks.checked_merge(orders, attrs, on="customer_id", expect="m:1")
    cust = pd.DataFrame({"customer_id": [1, 2], "region": ["x", "y"]})
    out = checks.checked_merge(orders, cust, on="customer_id", expect="m:1", how="left")
    assert len(out) == 2 and "region" in out


def test_split_overlap_and_time_leak():
    train = pd.DataFrame({"id": [1, 2, 3], "d": ["2024-01-01", "2024-02-01", "2024-03-01"]})
    test = pd.DataFrame({"id": [3, 4], "d": ["2024-03-01", "2024-04-01"]})
    assert not checks.split_overlap(train, test, key="id", quiet=True).passed
    assert checks.split_overlap(train, test.iloc[1:], key="id", quiet=True).passed
    assert not checks.time_leak(train, test, "d", quiet=True).passed
    assert checks.time_leak(train, test.iloc[1:], "d", quiet=True).passed


def test_target_proxy_flags_post_outcome_column():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 500)
    df = pd.DataFrame(
        {
            "target": y,
            "noise": rng.normal(size=500),
            "refund_days": np.where(y == 1, rng.integers(1, 30, 500), np.nan),
        }
    )
    r = checks.target_proxy(df, "target", quiet=True)
    assert "refund_days" in r.details["flagged"]
    assert "noise" not in r.details["flagged"]
    assert r.severity == "warning"


def test_censored_values_counts_markers_and_lt():
    s = pd.Series(["<0.5", "1.2", "ND", "0.8", "<1", "U", "2.0"])
    r = checks.censored_values(s, quiet=True)
    assert r.details["censored"] == 4
    assert r.details["lt_prefixed"] == 2 and r.details["markers"] == 2
    parsed = checks.parse_censored(s)
    assert parsed["censored"].sum() == 4
    assert parsed.loc[0, "limit"] == 0.5
    assert np.isnan(parsed.loc[0, "value"]) and parsed.loc[1, "value"] == 1.2


def test_results_are_appended_to_checks_file(tmp_path):
    df = pd.DataFrame({"id": [1, 2]})
    checks.unique_key(df, "id", quiet=True)
    checks.recount(df, df.iloc[:1], "filter", expect="fewer", quiet=True)
    rows = checks.read_checks(tmp_path / "checks.jsonl")
    assert [r["name"] for r in rows] == ["unique_key(id)", "recount(filter)"]
    assert all(r["passed"] for r in rows)
