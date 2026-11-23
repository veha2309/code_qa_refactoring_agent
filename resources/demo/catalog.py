"""Product catalogue used by the shop demo."""

PRODUCTS = {
    "book": {"name": "Notebook", "price": 100.0, "weight": 0.5},
    "pen": {"name": "Pen", "price": 20.0, "weight": 0.1},
    "bag": {"name": "Canvas bag", "price": 250.0, "weight": 0.8},
}


def product_details(sku):
    if sku not in PRODUCTS:
        raise ValueError(f"Unknown product: {sku}")
    return PRODUCTS[sku].copy()


def line_amount(sku, quantity):
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    return round(product_details(sku)["price"] * quantity, 2)


def line_weight(sku, quantity):
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    return round(product_details(sku)["weight"] * quantity, 2)
