import datetime as dt

from lxml import etree

from app.totals import compute_totals
from app.xml_builder import build_ecf_xml, build_rfce_xml
from tests.conftest import make_invoice


def test_e31_xml_contains_required_nodes():
    invoice = make_invoice()
    totals = compute_totals(invoice)
    xml = build_ecf_xml(invoice, totals)
    root = etree.fromstring(xml.encode("utf-8"))

    assert root.tag == "ECF"
    assert root.findtext("./Encabezado/IdDoc/TipoeCF") == "31"
    assert root.findtext("./Encabezado/IdDoc/eNCF") == "E310000000001"
    assert root.findtext("./Encabezado/IdDoc/FechaVencimientoSecuencia") == "31-12-2027"
    assert root.findtext("./Encabezado/IdDoc/IndicadorMontoGravado") == "0"
    assert root.findtext("./Encabezado/Emisor/FechaEmision") == "19-11-2026"
    assert root.findtext("./Encabezado/Comprador/RNCComprador") == "101672919"
    assert root.find("./DetallesItems/Item") is not None
    assert root.findtext("./DetallesItems/Item/IndicadorBienoServicio") == "2"
    assert root.findtext("FechaHoraFirma")
    assert "-" in root.findtext("FechaHoraFirma")


def test_e32_omits_fecha_vencimiento_even_if_provided():
    invoice = make_invoice(
        tipoe_cf=32,
        encf="E320000000001",
        fecha_vencimiento_secuencia=dt.date(2027, 12, 31),
        buyer=None,
    )
    assert invoice.fecha_vencimiento_secuencia is None
    totals = compute_totals(invoice)
    xml = build_ecf_xml(invoice, totals)
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.find("./Encabezado/IdDoc/FechaVencimientoSecuencia") is None
    assert root.find("./Encabezado/Comprador") is None
    assert root.findtext("./Encabezado/IdDoc/TipoeCF") == "32"


def test_credit_invoice_includes_fecha_limite_pago():
    invoice = make_invoice(
        tipo_pago=2,
        fecha_limite_pago=dt.date(2026, 12, 31),
        fecha_emision=dt.date(2026, 11, 19),
    )
    totals = compute_totals(invoice)
    xml = build_ecf_xml(invoice, totals)
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.findtext("./Encabezado/IdDoc/TipoPago") == "2"
    assert root.findtext("./Encabezado/IdDoc/FechaLimitePago") == "31-12-2026"


def test_credit_without_due_date_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="fecha_limite_pago"):
        make_invoice(tipo_pago=2, fecha_limite_pago=None)


def test_rfce_credit_includes_fecha_limite_pago():
    invoice = make_invoice(
        tipoe_cf=32,
        encf="E320000000003",
        buyer=None,
        tipo_pago=2,
        fecha_limite_pago=dt.date(2026, 12, 15),
    )
    totals = compute_totals(invoice)
    xml = build_rfce_xml(invoice, totals, "ABC123")
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.findtext("./Encabezado/IdDoc/FechaLimitePago") == "15-12-2026"
    assert root.find("./Encabezado/IdDoc/FechaVencimientoSecuencia") is None


def test_rfce_includes_security_code_from_full_ecf():
    invoice = make_invoice(
        tipoe_cf=32,
        encf="E320000000002",
        buyer=None,
    )
    totals = compute_totals(invoice)
    xml = build_rfce_xml(invoice, totals, "AbCdEf")
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.tag == "RFCE"
    assert root.find("./DetallesItems") is None
    assert root.findtext("./Encabezado/CodigoSeguridadeCF") == "AbCdEf"
