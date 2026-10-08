import pandas as pd

from cairn import profile


def test_profile_finds_keys_censoring_and_dates(tmp_path):
    df = pd.DataFrame(
        {
            "well_id": ["A", "A", "B", "B"],
            "date": ["2020-01-01", "2021-01-01", "2020-01-01", "2021-01-01"],
            "result": ["<0.5", "1.2", "ND", "1.2"],
            "value": [0.1, 1.2, 0.2, 1.2],
        }
    )
    p = tmp_path / "t.csv"
    df.to_csv(p, index=False)
    written = profile.profile_files([p], tmp_path / "profiles")
    prof = profile.profile_table(profile.read_table(p), "t", source=p)
    assert prof["rows"] == 4
    assert ["well_id", "date"] in prof["candidate_keys"]
    assert prof["fields"]["result"]["censoring_markers"] == {"lt_prefixed": 1, "markers": 1}
    assert "datetime" in prof["fields"]["date"]
    assert prof["fields"]["value"]["numeric"]["median"] == 0.7
    md = (tmp_path / "profiles" / "t.md").read_text()
    assert "CENSORED" in md and len(written) == 2
