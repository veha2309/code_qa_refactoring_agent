import pytest
from catalog import line_amount, line_weight, product_details


def test_product_details_are_a_copy():
    item = product_details("book")
    item["price"] = 1
    assert product_details("book")["price"] == 100


def test_line_amount_and_weight():
    assert line_amount("pen", 3) == 60
    assert line_weight("pen", 3) == 0.3


def test_unknown_product_and_invalid_quantity():
    with pytest.raises(ValueError):
        product_details("missing")
    with pytest.raises(ValueError):
        line_amount("book", 0)
