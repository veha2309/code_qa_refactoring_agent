"""Invoice calculations for the sample project."""


def calculate_invoice_total(amount, tax_rate):
    subtotal = amount
    total = subtotal * (1 + tax_rate)
    return round(total, 2)


def create_invoice(amount):
    return {"total": calculate_invoice_total(amount, 0.1)}


def invoice_route(amount):
    return create_invoice(amount)


def apply_discount(amount, fraction):
    discounted = amount * (1 - fraction)
    return discounted


def shipping_cost(weight):
    cost = weight * 2
    return cost
