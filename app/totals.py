"""ITBIS and invoice total calculations using Decimal half-up rounding."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.models import ITBIS_RATES, InvoiceInput, InvoiceTotals, LineItem

TWO = Decimal("0.01")
FOUR = Decimal("0.0001")


def money(value: Decimal) -> Decimal:
    return value.quantize(TWO, rounding=ROUND_HALF_UP)


def unit_price(value: Decimal) -> Decimal:
    return value.quantize(FOUR, rounding=ROUND_HALF_UP)


def format_money(value: Decimal) -> str:
    return f"{money(value):.2f}"


def format_unit_price(value: Decimal) -> str:
    quantized = unit_price(value)
    text = f"{quantized:.4f}".rstrip("0").rstrip(".")
    if "." not in text:
        return f"{text}.00"
    whole, frac = text.split(".", 1)
    if len(frac) == 1:
        return f"{whole}.{frac}0"
    return text


def format_quantity(value: Decimal) -> str:
    quantized = value.quantize(TWO, rounding=ROUND_HALF_UP)
    text = f"{quantized:.2f}".rstrip("0").rstrip(".")
    return text if text else "0"


def line_amount(item: LineItem) -> Decimal:
    return money(item.quantity * unit_price(item.unit_price))


def compute_totals(invoice: InvoiceInput) -> InvoiceTotals:
    totals = InvoiceTotals()
    for item in invoice.items:
        amount = line_amount(item)
        if item.tax_indicator == 1:
            totals.monto_gravado_i1 += amount
        elif item.tax_indicator == 2:
            totals.monto_gravado_i2 += amount
        elif item.tax_indicator == 3:
            totals.monto_gravado_i3 += amount
        else:
            totals.monto_exento += amount

    totals.monto_gravado_i1 = money(totals.monto_gravado_i1)
    totals.monto_gravado_i2 = money(totals.monto_gravado_i2)
    totals.monto_gravado_i3 = money(totals.monto_gravado_i3)
    totals.monto_exento = money(totals.monto_exento)
    totals.monto_gravado_total = money(
        totals.monto_gravado_i1 + totals.monto_gravado_i2 + totals.monto_gravado_i3
    )
    totals.total_itbis_1 = money(totals.monto_gravado_i1 * ITBIS_RATES[1])
    totals.total_itbis_2 = money(totals.monto_gravado_i2 * ITBIS_RATES[2])
    totals.total_itbis_3 = money(totals.monto_gravado_i3 * ITBIS_RATES[3])
    totals.total_itbis = money(
        totals.total_itbis_1 + totals.total_itbis_2 + totals.total_itbis_3
    )
    totals.monto_total = money(
        totals.monto_gravado_total + totals.monto_exento + totals.total_itbis
    )
    return totals
