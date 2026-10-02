import pytest
from numberkit.bounds import clamp, normalize
from numberkit.stats import mean, weighted_mean


def test_contract():
    assert mean([7]) == 7
    assert mean(iter([1, 2, 3])) == 2
    assert mean([-2, 2]) == 0
