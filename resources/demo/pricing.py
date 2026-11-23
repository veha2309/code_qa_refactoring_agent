"""Price an order using the catalogue, promotion and invoice rules."""
from catalog import line_amount, line_weight
from delivery import delivery_fee
from invoice import calculate_invoice_total
from promotions import discount_amount


def order_subtotal(items):
    return round(sum(line_amount(sku, quantity) for sku, quantity in items), 2)


def order_weight(items):
    return round(sum(line_weight(sku, quantity) for sku, quantity in items), 2)


def quote_order(items, promo_code=None, tax_rate=0.1):
    if not items:
        raise ValueError("An order needs at least one item")
    subtotal = order_subtotal(items)
    discount = discount_amount(subtotal, promo_code)
    discounted = round(subtotal - discount, 2)
    taxed = calculate_invoice_total(discounted, tax_rate)
    shipping = delivery_fee(discounted, order_weight(items))
    return {"subtotal": subtotal, "discount": discount, "taxed": taxed,
            "shipping": shipping, "total": round(taxed + shipping, 2)}
