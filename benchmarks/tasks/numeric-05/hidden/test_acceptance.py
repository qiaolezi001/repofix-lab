import pytest
from numberkit.bounds import clamp, normalize
from numberkit.stats import mean, weighted_mean


def test_contract():
    assert normalize([9]) == [0.0]
    assert normalize([]) == []
    assert normalize([2, 4, 6]) == [0.0, 0.5, 1.0]
