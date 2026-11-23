"""Return calculation for a confirmed order."""
from orders import order_total


def refundable_amount(order, fraction=1.0):
    if not 0 <= fraction <= 1:
        raise ValueError("Refund fraction must be between zero and one")
    return round(order_total(order) * fraction, 2)
