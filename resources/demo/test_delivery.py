from delivery import delivery_fee, delivery_label


def test_standard_shipping_uses_weight():
    assert delivery_fee(100, 2) == 4
    assert delivery_label(4) == "standard"


def test_free_shipping_at_threshold():
    assert delivery_fee(300, 2) == 0
    assert delivery_label(0) == "free"


def test_below_threshold_is_not_free():
    assert delivery_fee(299.99, 1) == 2
