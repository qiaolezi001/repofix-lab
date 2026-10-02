import pytest
from shopkit.money import discounted_price
from shopkit.cart import subtotal
from shopkit.inventory import reserve
from shopkit.paging import paginate


def test_contract():
    assert reserve(3, 0) == 3
    assert reserve(3, 3) == 0
    with pytest.raises(ValueError):
        reserve(3, 4)
    with pytest.raises(ValueError):
        reserve(0, -1)
