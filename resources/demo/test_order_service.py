from order_service import checkout


def test_checkout_applies_discount_tax_and_shipping():
    assert checkout(100, 0.2, 3) == {"total": 94.0}


def test_checkout_without_discount_or_shipping():
    assert checkout(50, 0, 0) == {"total": 55.0}
