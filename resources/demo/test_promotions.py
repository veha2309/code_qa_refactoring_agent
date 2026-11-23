import pytest
from promotions import discount_amount, discount_rate


def test_no_discount():
    assert discount_rate(None) == 0


def test_known_discount():
    assert discount_amount(200, "SAVE10") == 20
    assert discount_amount(125, "MEMBER20") == 25


def test_unknown_discount_is_rejected():
    with pytest.raises(ValueError):
        discount_rate("INVALID")
