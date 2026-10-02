import pytest
from textkit.core import normalize_whitespace, truncate, split_pair, slugify
from textkit.matching import count_token


def test_contract():
    assert slugify("--A___B--") == "a-b"
    assert slugify("!!!") == ""
    assert slugify("abc123") == "abc123"
