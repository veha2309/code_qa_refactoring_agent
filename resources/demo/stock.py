"""Stock checks; the demo never mutates a real inventory."""


def check_availability(items, available):
    """Aggregate duplicate lines before comparing the requested quantities."""
    requested = {}
    for sku, quantity in items:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        requested[sku] = requested.get(sku, 0) + quantity
    return {sku: quantity for sku, quantity in requested.items()
            if quantity > available.get(sku, 0)}


def is_available(items, available):
    return not check_availability(items, available)
