from invoice import calculate_invoice_total, create_invoice, invoice_route, apply_discount, shipping_cost


def test_invoice_tax():
    assert calculate_invoice_total(100, 0.1) == 110


def test_invoice_zero():
    assert calculate_invoice_total(0, 0.1) == 0


def test_invoice_rounding():
    assert calculate_invoice_total(1.15, 0.1) == 1.26


def test_invoice_service():
    assert create_invoice(100) == {"total": 110}


def test_invoice_route():
    assert invoice_route(50) == {"total": 55}


def test_discount():
    assert apply_discount(100, 0.2) == 80


def test_shipping():
    assert shipping_cost(3) == 6

