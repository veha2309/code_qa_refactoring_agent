"""A small checkout flow for exploring cross-file change impact."""
from invoice import calculate_invoice_total, apply_discount, shipping_cost


def checkout(amount, discount_fraction, weight):
    """Apply a discount, add tax, and include shipping."""
    discounted = apply_discount(amount, discount_fraction)
    taxed = calculate_invoice_total(discounted, 0.1)
    return {"total": round(taxed + shipping_cost(weight), 2)}
