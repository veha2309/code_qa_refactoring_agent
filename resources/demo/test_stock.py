import pytest
from stock import check_availability, is_available


def test_sufficient_inventory():
    assert is_available([("book", 2)], {"book": 2})


def test_duplicate_lines_are_combined():
    assert check_availability([("pen", 2), ("pen", 2)], {"pen": 3}) == {"pen": 4}


def test_missing_stock_is_unavailable():
    assert not is_available([("book", 1)], {})


def test_invalid_quantity_is_rejected():
    with pytest.raises(ValueError):
        check_availability([("book", 0)], {"book": 1})
