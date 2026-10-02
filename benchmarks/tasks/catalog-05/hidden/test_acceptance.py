import pytest
from shopkit.money import discounted_price
from shopkit.cart import subtotal
from shopkit.inventory import reserve
from shopkit.paging import paginate


def test_contract():
    assert subtotal([{"price": 2, "quantity": 3}, {"price": 4, "quantity": 1}]) == 10
    assert subtotal(iter([{"price": 2, "quantity": 3}])) == 6
