import pytest
from shopkit.money import discounted_price
from shopkit.cart import subtotal
from shopkit.inventory import reserve
from shopkit.paging import paginate


def test_contract():
    assert subtotal([{"price": 2.5, "quantity": 2}, {"price": 4, "quantity": 0}]) == 5
    assert subtotal([]) == 0
    with pytest.raises(ValueError):
        subtotal([{"price": 3, "quantity": -1}])
