from decimal import Decimal

from app.models import LineItem
from app.totals import compute_totals
from tests.conftest import make_invoice


def test_itbis_18_percent():
    invoice = make_invoice(
        items=[
            LineItem(
                name="A",
                quantity="2",
                unit_price="100.00",
                tax_indicator=1,
            )
        ]
    )
    totals = compute_totals(invoice)
    assert totals.monto_gravado_i1 == Decimal("200.00")
    assert totals.total_itbis_1 == Decimal("36.00")
    assert totals.monto_total == Decimal("236.00")


def test_itbis_16_and_exempt_mixed():
    invoice = make_invoice(
        items=[
            LineItem(name="B", quantity="1", unit_price="100.00", tax_indicator=2),
            LineItem(name="C", quantity="1", unit_price="50.00", tax_indicator=4),
        ]
    )
    totals = compute_totals(invoice)
    assert totals.monto_gravado_i2 == Decimal("100.00")
    assert totals.total_itbis_2 == Decimal("16.00")
    assert totals.monto_exento == Decimal("50.00")
    assert totals.monto_total == Decimal("166.00")


def test_tax_indicator_3_zero_rate():
    invoice = make_invoice(
        items=[LineItem(name="D", quantity="1", unit_price="80.00", tax_indicator=3)]
    )
    totals = compute_totals(invoice)
    assert totals.monto_gravado_i3 == Decimal("80.00")
    assert totals.total_itbis_3 == Decimal("0.00")
    assert totals.monto_total == Decimal("80.00")
