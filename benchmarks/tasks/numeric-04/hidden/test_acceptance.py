import pytest
from numberkit.bounds import clamp, normalize
from numberkit.stats import mean, weighted_mean


def test_contract():
    assert weighted_mean([2, 8], [2, 2]) == 5
    assert weighted_mean([3], [0.5]) == 3
    with pytest.raises(ValueError):
        weighted_mean([1, 2], [0, 0])
