"""Shipping rules for the sample store."""
from invoice import shipping_cost

FREE_SHIPPING_THRESHOLD = 300.0


def delivery_fee(subtotal, weight):
    if subtotal >= FREE_SHIPPING_THRESHOLD:
        return 0.0
    return round(shipping_cost(weight), 2)


def delivery_label(fee):
    return "free" if fee == 0 else "standard"
