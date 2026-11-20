"""Build unsigned ECF and RFCE XML documents for DGII."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from lxml import etree

from app.models import InvoiceInput, InvoiceTotals
from app.totals import format_money, format_quantity, format_unit_price, line_amount

DR_TZ = ZoneInfo("America/Santo_Domingo")


def format_date(value: date) -> str:
    return value.strftime("%d-%m-%Y")


def format_datetime(value: datetime) -> str:
    return value.strftime("%d-%m-%Y %H:%M:%S")


def now_dr() -> datetime:
    return datetime.now(DR_TZ).replace(tzinfo=None)


def _el(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    child = etree.SubElement(parent, tag)
    if text is not None:
        child.text = text
    return child


def _append_totals(parent: etree._Element, totals: InvoiceTotals) -> None:
    totales = _el(parent, "Totales")
    if totals.monto_gravado_total > 0:
        _el(totales, "MontoGravadoTotal", format_money(totals.monto_gravado_total))
    if totals.monto_gravado_i1 > 0:
        _el(totales, "MontoGravadoI1", format_money(totals.monto_gravado_i1))
    if totals.monto_gravado_i2 > 0:
        _el(totales, "MontoGravadoI2", format_money(totals.monto_gravado_i2))
    if totals.monto_gravado_i3 > 0:
        _el(totales, "MontoGravadoI3", format_money(totals.monto_gravado_i3))
    if totals.monto_exento > 0:
        _el(totales, "MontoExento", format_money(totals.monto_exento))
    if totals.monto_gravado_i1 > 0:
        _el(totales, "ITBIS1", "18")
    if totals.monto_gravado_i2 > 0:
        _el(totales, "ITBIS2", "16")
    if totals.monto_gravado_i3 > 0:
        _el(totales, "ITBIS3", "0")
    if totals.total_itbis > 0 or totals.monto_gravado_total > 0:
        _el(totales, "TotalITBIS", format_money(totals.total_itbis))
    if totals.monto_gravado_i1 > 0:
        _el(totales, "TotalITBIS1", format_money(totals.total_itbis_1))
    if totals.monto_gravado_i2 > 0:
        _el(totales, "TotalITBIS2", format_money(totals.total_itbis_2))
    if totals.monto_gravado_i3 > 0:
        _el(totales, "TotalITBIS3", format_money(totals.total_itbis_3))
    _el(totales, "MontoTotal", format_money(totals.monto_total))


def build_ecf_xml(
    invoice: InvoiceInput,
    totals: InvoiceTotals,
    *,
    fecha_firma: datetime | None = None,
) -> str:
    """Return an unsigned ECF XML string (no XML declaration)."""
    firma = fecha_firma or now_dr()
    emision = invoice.fecha_emision or firma.date()

    root = etree.Element("ECF")
    encabezado = _el(root, "Encabezado")
    _el(encabezado, "Version", "1.0")

    id_doc = _el(encabezado, "IdDoc")
    _el(id_doc, "TipoeCF", str(invoice.tipoe_cf))
    _el(id_doc, "eNCF", invoice.encf)
    # Obligation code 0 for E32: must not include FechaVencimientoSecuencia.
    if invoice.tipoe_cf == 31 and invoice.fecha_vencimiento_secuencia is not None:
        _el(
            id_doc,
            "FechaVencimientoSecuencia",
            format_date(invoice.fecha_vencimiento_secuencia),
        )
    if any(item.tax_indicator in (1, 2, 3) for item in invoice.items):
        _el(id_doc, "IndicadorMontoGravado", "0")
    _el(id_doc, "TipoIngresos", invoice.tipo_ingresos)
    _el(id_doc, "TipoPago", str(invoice.tipo_pago))
    if invoice.tipo_pago == 2 and invoice.fecha_limite_pago is not None:
        _el(id_doc, "FechaLimitePago", format_date(invoice.fecha_limite_pago))

    emisor = _el(encabezado, "Emisor")
    _el(emisor, "RNCEmisor", invoice.issuer.rnc)
    _el(emisor, "RazonSocialEmisor", invoice.issuer.name)
    _el(emisor, "DireccionEmisor", invoice.issuer.address or "")
    _el(emisor, "FechaEmision", format_date(emision))

    if invoice.buyer is not None:
        comprador = _el(encabezado, "Comprador")
        _el(comprador, "RNCComprador", invoice.buyer.rnc)
        _el(comprador, "RazonSocialComprador", invoice.buyer.name)
        if invoice.buyer.address:
            _el(comprador, "DireccionComprador", invoice.buyer.address)

    _append_totals(encabezado, totals)

    detalles = _el(root, "DetallesItems")
    for index, item in enumerate(invoice.items, start=1):
        node = _el(detalles, "Item")
        _el(node, "NumeroLinea", str(index))
        _el(node, "IndicadorFacturacion", str(item.tax_indicator))
        _el(node, "NombreItem", item.name)
        _el(node, "IndicadorBienoServicio", str(item.good_or_service))
        if item.description:
            _el(node, "DescripcionItem", item.description)
        _el(node, "CantidadItem", format_quantity(item.quantity))
        _el(node, "PrecioUnitarioItem", format_unit_price(item.unit_price))
        _el(node, "MontoItem", format_money(line_amount(item)))

    _el(root, "FechaHoraFirma", format_datetime(firma))
    return etree.tostring(root, encoding="unicode")


def build_rfce_xml(
    invoice: InvoiceInput,
    totals: InvoiceTotals,
    codigo_seguridad: str,
) -> str:
    """Build unsigned RFCE summary for E32 under RD$250,000."""
    emision = invoice.fecha_emision or now_dr().date()

    root = etree.Element("RFCE")
    encabezado = _el(root, "Encabezado")
    _el(encabezado, "Version", "1.0")

    id_doc = _el(encabezado, "IdDoc")
    _el(id_doc, "TipoeCF", str(invoice.tipoe_cf))
    _el(id_doc, "eNCF", invoice.encf)
    _el(id_doc, "TipoIngresos", invoice.tipo_ingresos)
    _el(id_doc, "TipoPago", str(invoice.tipo_pago))
    if invoice.tipo_pago == 2 and invoice.fecha_limite_pago is not None:
        _el(id_doc, "FechaLimitePago", format_date(invoice.fecha_limite_pago))

    emisor = _el(encabezado, "Emisor")
    _el(emisor, "RNCEmisor", invoice.issuer.rnc)
    _el(emisor, "RazonSocialEmisor", invoice.issuer.name)
    _el(emisor, "FechaEmision", format_date(emision))

    if invoice.buyer is not None:
        comprador = _el(encabezado, "Comprador")
        _el(comprador, "RNCComprador", invoice.buyer.rnc)
        _el(comprador, "RazonSocialComprador", invoice.buyer.name)

    _append_totals(encabezado, totals)
    _el(encabezado, "CodigoSeguridadeCF", codigo_seguridad)
    return etree.tostring(root, encoding="unicode")


def with_xml_declaration(body: str) -> str:
    return f'<?xml version="1.0" encoding="utf-8"?>{body}'
