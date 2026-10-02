import pytest
from textkit.core import normalize_whitespace, truncate, split_pair, slugify
from textkit.matching import count_token


def test_contract():
    assert slugify("Hello,  World!") == "hello-world"


def test_regressions():
    assert normalize_whitespace("hello") == "hello"
    assert split_pair("x=y") == ("x", "y")
    assert slugify("abc") == "abc"
