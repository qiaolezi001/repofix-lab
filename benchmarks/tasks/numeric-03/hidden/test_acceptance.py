import pytest
from numberkit.bounds import clamp, normalize
from numberkit.stats import mean, weighted_mean


def test_contract():
    with pytest.raises(ValueError):
        mean(iter([]))
    assert mean([0]) == 0
