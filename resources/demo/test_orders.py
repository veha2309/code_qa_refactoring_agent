import pytest
from orders import order_total, place_order


def test_confirmed_order_uses_pricing():
    order = place_order([("book", 1)], {"book": 2}, "SAVE10")
    assert order["status"] == "confirmed"
    assert order_total(order) == 100


def test_shortage_does_not_produce_a_quote():
    order = place_order([("book", 3)], {"book": 2})
    assert order == {"status": "out_of_stock", "shortages": {"book": 3}}
    assert order_total(order) == 0


def test_empty_order_is_rejected():
    with pytest.raises(ValueError):
        place_order([], {})
