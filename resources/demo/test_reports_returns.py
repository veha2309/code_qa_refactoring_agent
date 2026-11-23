import pytest
from orders import place_order
from reports import confirmed_count, revenue, sales_summary
from returns import refundable_amount


def test_summary_counts_only_confirmed_sales():
    success = place_order([("book", 1)], {"book": 1})
    failed = place_order([("pen", 3)], {"pen": 1})
    assert confirmed_count([success, failed]) == 1
    assert revenue([success, failed]) == 111
    assert sales_summary([success, failed]) == {"orders": 1, "revenue": 111}


def test_partial_and_failed_order_refunds():
    order = place_order([("book", 1)], {"book": 1})
    assert refundable_amount(order, 0.5) == 55.5
    assert refundable_amount({"status": "out_of_stock"}) == 0


def test_invalid_refund_fraction():
    with pytest.raises(ValueError):
        refundable_amount({"status": "out_of_stock"}, 1.1)
