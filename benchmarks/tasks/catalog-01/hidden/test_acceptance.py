import pytest
from shopkit.money import discounted_price
from shopkit.cart import subtotal
from shopkit.inventory import reserve
from shopkit.paging import paginate


def test_contract():
    assert discounted_price(10, 0) == 10
    assert discounted_price(10, 100) == 0
    with pytest.raises(ValueError):
        discounted_price(10, 101)
