import pytest
from pagination import paginate


def test_first_page():
    assert paginate([0, 1, 2, 3, 4], 1, 2) == [0, 1]


def test_pages_do_not_overlap():
    assert paginate([0, 1, 2, 3, 4], 2, 2) == [2, 3]
    assert paginate([0, 1, 2, 3, 4], 3, 2) == [4]


def test_invalid_page():
    with pytest.raises(ValueError):
        paginate([1], 0, 2)
