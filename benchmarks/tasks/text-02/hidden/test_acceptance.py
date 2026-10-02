import pytest
from textkit.core import normalize_whitespace, truncate, split_pair, slugify
from textkit.matching import count_token


def test_contract():
    assert truncate("hello", 0) == ""
    assert truncate("hello", 8) == "hello"
    assert truncate("你好世界", 2) == "你好"
    with pytest.raises(ValueError):
        truncate("x", -1)
