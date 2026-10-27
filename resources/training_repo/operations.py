"""Synthetic training domain, intentionally separate from invoice evaluation."""


def add_stock(quantity, incoming):
    return quantity + incoming


def remove_stock(quantity, outgoing):
    return quantity - outgoing


def stock_available(quantity):
    return quantity > 0


def catalog_price(price, multiplier):
    return price * multiplier


def normalize_username(username):
    return username.strip().lower()


def validate_username(username):
    return len(normalize_username(username)) >= 3


def temperature_celsius(fahrenheit):
    return (fahrenheit - 32) * 5 / 9


def area_rectangle(width, height):
    return width * height

