"""Order workflow connecting stock validation to pricing."""
from pricing import quote_order
from stock import check_availability


def place_order(items, available, promo_code=None):
    if not items:
        raise ValueError("An order needs at least one item")
    shortages = check_availability(items, available)
    if shortages:
        return {"status": "out_of_stock", "shortages": shortages}
    return {"status": "confirmed", "quote": quote_order(items, promo_code)}


def order_total(order):
    if order["status"] != "confirmed":
        return 0.0
    return order["quote"]["total"]
