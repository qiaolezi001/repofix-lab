import pytest
from shopkit.money import discounted_price
from shopkit.cart import subtotal
from shopkit.inventory import reserve
from shopkit.paging import paginate


def test_contract():
    assert paginate([0, 1, 2, 3, 4], 2, 2) == [2, 3]
    assert paginate([0, 1, 2, 3, 4], 3, 2) == [4]
    assert paginate([], 1, 2) == []
    with pytest.raises(ValueError):
        paginate([1], 0, 2)
