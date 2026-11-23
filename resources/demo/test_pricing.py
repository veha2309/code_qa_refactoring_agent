import pytest
from pricing import order_subtotal, order_weight, quote_order


def test_order_totals_multiple_lines():
    items = [("book", 2), ("pen", 2)]
    assert order_subtotal(items) == 240
    assert order_weight(items) == 1.2


def test_quote_with_discount_tax_and_shipping():
    quote = quote_order([("book", 2), ("pen", 2)], "SAVE10")
    assert quote == {"subtotal": 240, "discount": 24, "taxed": 237.6,
                     "shipping": 2.4, "total": 240.0}


def test_quote_gets_free_shipping_after_discount():
    assert quote_order([("bag", 2)], "MEMBER20")["shipping"] == 0


def test_discount_can_move_order_below_shipping_threshold():
    assert quote_order([("book", 3)], "SAVE10")["shipping"] == 3


def test_empty_order_is_rejected():
    with pytest.raises(ValueError):
        quote_order([])
