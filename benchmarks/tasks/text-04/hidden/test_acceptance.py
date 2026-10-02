import pytest
from textkit.core import normalize_whitespace, truncate, split_pair, slugify
from textkit.matching import count_token


def test_contract():
    assert count_token("ONE, one! OnE", "ONE") == 3
    assert count_token("cat scatter CAT", "cat") == 2
    assert count_token("", "x") == 0
