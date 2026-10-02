import pytest
from textkit.core import normalize_whitespace, truncate, split_pair, slugify
from textkit.matching import count_token


def test_contract():
    assert normalize_whitespace("a\nb\r\nc") == "a b c"
    assert normalize_whitespace(" \t") == ""
    assert normalize_whitespace("x") == "x"
