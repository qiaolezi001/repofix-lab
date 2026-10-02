import pytest
from numberkit.bounds import clamp, normalize
from numberkit.stats import mean, weighted_mean


def test_contract():
    assert normalize([5, 5]) == [0.0, 0.0]


def test_regressions():
    assert clamp(10, 0, 10) == 10
    assert normalize([0, 10]) == [0, 1]
    with pytest.raises(ValueError):
        weighted_mean([1], [1, 2])
