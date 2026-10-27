from operations import add_stock, remove_stock, stock_available, catalog_price
from operations import normalize_username, validate_username, temperature_celsius, area_rectangle


def test_add_stock():
    assert add_stock(3, 2) == 5


def test_add_empty_stock():
    assert add_stock(0, 2) == 2


def test_remove_stock():
    assert remove_stock(3, 2) == 1


def test_stock_available():
    assert stock_available(1)


def test_catalog_price():
    assert catalog_price(10, 2) == 20


def test_normalize_username():
    assert normalize_username(" ABC ") == "abc"


def test_validate_username():
    assert validate_username("abc")


def test_short_username():
    assert not validate_username("a")


def test_temperature_celsius():
    assert temperature_celsius(32) == 0


def test_area_rectangle():
    assert area_rectangle(2, 3) == 6

