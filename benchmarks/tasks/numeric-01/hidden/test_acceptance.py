import pytest
from numberkit.bounds import clamp, normalize
from numberkit.stats import mean, weighted_mean


def test_contract():
    assert clamp(11, 0, 10) == 10
    assert clamp(-4, -3, -1) == -3
    assert clamp(5, 5, 5) == 5
