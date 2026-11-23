"""Simple reporting over completed in-memory sample orders."""
from orders import order_total


def revenue(orders):
    return round(sum(order_total(order) for order in orders), 2)


def confirmed_count(orders):
    return sum(1 for order in orders if order["status"] == "confirmed")


def sales_summary(orders):
    return {"orders": confirmed_count(orders), "revenue": revenue(orders)}
