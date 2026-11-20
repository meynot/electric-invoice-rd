from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from lxml import etree

from app.models import LineItem
from app.qr import build_ecf_qr_url, build_fc_qr_url
from app.service import emit_invoice
from app.signer import extract_security_code
from app.totals import compute_totals
from app.xml_builder import build_ecf_xml
from tests.conftest import make_invoice


def test_signature_shape_rsa_sha256_empty_uri(signer):
    invoice = make_invoice()
    totals = compute_totals(invoice)
    unsigned = build_ecf_xml(invoice, totals)
    signed = signer.sign_xml(unsigned)
    root = etree.fromstring(signed.encode("utf-8"))

    ns = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
    signature = root.find("ds:Signature", ns)
    assert signature is not None
    method = signature.find("ds:SignedInfo/ds:SignatureMethod", ns)
    assert (
        method.get("Algorithm")
        == "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
    )
    reference = signature.find("ds:SignedInfo/ds:Reference", ns)
    assert reference.get("URI") == ""
    digest = signature.find("ds:SignedInfo/ds:Reference/ds:DigestMethod", ns)
    assert digest.get("Algorithm") == "http://www.w3.org/2001/04/xmlenc#sha256"
    assert signature.find("ds:KeyInfo/ds:X509Data/ds:X509Certificate", ns) is not None
    code = extract_security_code(signed)
    assert len(code) == 6


def test_small_e32_routes_to_rfce(settings, signer):
    invoice = make_invoice(
        tipoe_cf=32,
        encf="E320000000010",
        buyer=None,
        dry_run=True,
        items=[
            LineItem(name="Cafe", quantity="1", unit_price="100.00", tax_indicator=1)
        ],
    )
    result = emit_invoice(invoice, settings, signer=signer)
    assert result.used_rfce is True
    assert result.sent_payload_path is not None
    assert "RFCE" in result.sent_payload_path
    rfce = open(result.sent_payload_path, encoding="utf-8").read()
    assert f"<CodigoSeguridadeCF>{result.codigo_seguridad}</CodigoSeguridadeCF>" in rfce
    assert "consultatimbrefc" in result.qr_url.lower()


def test_large_e32_requires_buyer_and_uses_full_ecf(settings, signer):
    invoice = make_invoice(
        tipoe_cf=32,
        encf="E320000000011",
        dry_run=True,
        items=[
            LineItem(
                name="Equipo",
                quantity="1",
                unit_price="250000.00",
                tax_indicator=4,
            )
        ],
    )
    result = emit_invoice(invoice, settings, signer=signer)
    assert result.used_rfce is False
    assert result.monto_total == Decimal("250000.00")
    assert "consultatimbre" in result.qr_url.lower()
    assert "consultatimbrefc" not in result.qr_url.lower()


def test_buyer_required_for_e32_at_threshold(settings, signer):
    invoice = make_invoice(
        tipoe_cf=32,
        encf="E320000000012",
        buyer=None,
        dry_run=True,
        items=[
            LineItem(
                name="Equipo",
                quantity="1",
                unit_price="250000.00",
                tax_indicator=4,
            )
        ],
    )
    import pytest
    from app.service import InvoiceValidationError

    with pytest.raises(InvoiceValidationError):
        emit_invoice(invoice, settings, signer=signer)


def test_qr_query_strings():
    ecf = build_ecf_qr_url(
        env="testecf",
        rnc_emisor="131880738",
        rnc_comprador="101672919",
        encf="E310000000001",
        fecha_emision="19-11-2026",
        monto_total=Decimal("236.00"),
        fecha_firma="19-11-2026 10:00:00",
        codigo_seguridad="Ab12Cd",
    )
    parsed = urlparse(ecf)
    assert parsed.path.endswith("/consultatimbre")
    qs = parse_qs(parsed.query)
    assert qs["RncEmisor"] == ["131880738"]
    assert qs["RncComprador"] == ["101672919"]
    assert qs["MontoTotal"] == ["236.00"]
    assert qs["CodigoSeguridad"] == ["Ab12Cd"]

    fc = build_fc_qr_url(
        env="testecf",
        rnc_emisor="131880738",
        encf="E320000000001",
        monto_total=Decimal("118.00"),
        codigo_seguridad="XyZ901",
    )
    parsed_fc = urlparse(fc)
    assert parsed_fc.path.endswith("/consultatimbrefc")
    qs_fc = parse_qs(parsed_fc.query)
    assert "RncComprador" not in qs_fc
    assert qs_fc["CodigoSeguridad"] == ["XyZ901"]
