from repofix.index import Index


def test_ast_symbols_and_bm25_order(tmp_path):
    (tmp_path / "calc.py").write_text(
        "class Calculator:\n    def divide(self, numerator, denominator):\n        return numerator / denominator\n",
        encoding="utf-8",
    )
    (tmp_path / "strings.py").write_text(
        "def reverse(text):\n    return text[::-1]\n", encoding="utf-8"
    )
    index = Index(tmp_path, "baseline-v1")
    results = index.search("divide denominator", limit=3)
    assert results[0]["path"] == "calc.py"
    assert any(item["symbol"] == "Calculator.divide" for item in results)
    assert results[0]["version"] == "baseline-v1"
    assert results[0]["start_line"] >= 1
    assert index.search("totallyunrelatedterm") == []
    assert index.search(" ") == []


def test_syntax_error_is_visible_and_retrievable(tmp_path):
    (tmp_path / "broken.py").write_text("def normalize(\n", encoding="utf-8")
    index = Index(tmp_path, "v1")
    assert any("Syntax error" in warning for warning in index.warnings)
    assert index.search("normalize")[0]["symbol"] == "<syntax-error>"


def test_large_function_is_split_with_real_line_ranges(tmp_path):
    (tmp_path / "long.py").write_text(
        "def long_function():\n" + "    value = 1\n" * 240, encoding="utf-8"
    )
    index = Index(tmp_path, "v1")
    chunks = [chunk for chunk in index.chunks if chunk["symbol"] == "long_function"]
    assert [(chunk["start_line"], chunk["end_line"]) for chunk in chunks] == [
        (1, 100),
        (101, 200),
        (201, 241),
    ]
    assert all(
        len(chunk["text"].splitlines()) == chunk["end_line"] - chunk["start_line"] + 1
        for chunk in chunks
    )
