import pytest
from textkit.core import normalize_whitespace, truncate, split_pair, slugify
from textkit.matching import count_token


def test_contract():
    assert split_pair("a=b=c") == ("a", "b=c")
    assert split_pair("a=") == ("a", "")
    with pytest.raises(ValueError):
        split_pair("missing", ":")
