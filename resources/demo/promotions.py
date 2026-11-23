"""Discount rules separated from the checkout caller."""

DISCOUNT_RATES = {"SAVE10": 0.10, "MEMBER20": 0.20}


def discount_rate(code):
    if not code:
        return 0.0
    if code not in DISCOUNT_RATES:
        raise ValueError(f"Unknown promotion: {code}")
    return DISCOUNT_RATES[code]


def discount_amount(subtotal, code):
    return round(subtotal * discount_rate(code), 2)
