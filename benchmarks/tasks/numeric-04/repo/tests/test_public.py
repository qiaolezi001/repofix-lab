import pytest
from numberkit.bounds import clamp, normalize
from numberkit.stats import mean, weighted_mean


def test_contract():
    assert weighted_mean([10, 20], [1, 3]) == 17.5


def test_regressions():
    assert clamp(10, 0, 10) == 10
    assert normalize([0, 10]) == [0, 1]
    with pytest.raises(ValueError):
        weighted_mean([1], [1, 2])
