from cairn import numbers


def test_record_and_render(tmp_path, monkeypatch):
    ledger = tmp_path / "numbers.json"
    monkeypatch.setenv("CAIRN_LEDGER", str(ledger))
    numbers.record("a.median", 2.345678, unit="ug/L", n=12)
    numbers.record("a.n", 12)
    data = numbers.load_ledger(ledger)
    assert data["a.median"]["unit"] == "ug/L" and data["a.n"]["value"] == 12
    text, missing = numbers.render("median {{a.median:.2f}} over {{ a.n }} wells {{nope}}", data)
    assert text == "median 2.35 over 12 wells {{nope}}"
    assert missing == ["nope"]


def test_record_rejects_bad_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("CAIRN_LEDGER", str(tmp_path / "n.json"))
    import pytest

    with pytest.raises(ValueError):
        numbers.record("has space", 1)


def test_bare_numbers_heuristic():
    tmpl = """# Report 2024
1. Step one
The median was 2.3 ug/L in 2021 and {{a.median}} now; n=12.
`code 99` and
```
x = 42
```
Rate rose 15%.
"""
    found = numbers.bare_numbers(tmpl)
    lits = [lit for _, lit in found]
    assert "2.3" in lits and "12" in lits and "15%" in lits
    assert "2024" not in lits and "2021" not in lits and "99" not in lits and "42" not in lits
