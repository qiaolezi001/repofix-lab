import pytest
from shopkit.money import discounted_price
from shopkit.cart import subtotal
from shopkit.inventory import reserve
from shopkit.paging import paginate


def test_contract():
    assert paginate([0, 1, 2, 3, 4], 1, 2) == [0, 1]


def test_regressions():
    assert reserve(10, 2) == 8
    with pytest.raises(ValueError):
        discounted_price(-1, 5)
    with pytest.raises(ValueError):
        paginate([1], 1, 0)
