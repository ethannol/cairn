from pathlib import Path

from cairn import lint


def _codes(src: str) -> list[str]:
    return [i.code for i in lint.lint_source(src, Path("s.py"))]


def test_merge_without_validate_is_error():
    assert "C101" in _codes("import pandas as pd\nout = a.merge(b, on='k')\n")
    assert "C101" in _codes("import pandas as pd\nout = pd.merge(a, b, on='k')\n")
    assert "C101" not in _codes("out = a.merge(b, on='k', validate='m:1')\n")
    assert "C101" not in _codes(
        "from cairn import checked_merge\nout = checked_merge(a, b, on='k')\n"
    )


def test_warnings():
    codes = _codes(
        "df['x'] = df['x'].fillna(0)\nX_tr, X_te = train_test_split(X)\n"
        "scaler.fit_transform(X)\nprint('lift of 12%')\n"
    )
    assert {"C201", "C301", "C302", "C401"} <= set(codes)
    assert all(i.severity == "warning" for i in lint.lint_source("df.fillna(0)\n", Path("s.py")))


def test_syntax_error_reported():
    assert _codes("def (:\n") == ["C000"]
