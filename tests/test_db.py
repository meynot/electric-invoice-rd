from app.db import InvoiceDatabase, format_invoice_number
from app.service import emit_invoice
from tests.conftest import make_invoice


def test_format_invoice_number(settings):
    settings.invoice_number_prefix = "INV-"
    settings.invoice_number_digits = 5
    settings.invoice_number_format = "00000"
    assert format_invoice_number(1, settings) == "INV-00001"
    assert format_invoice_number(42, settings) == "INV-00042"


def test_sequence_increments_from_env(settings):
    settings.invoice_number_start = 1
    settings.invoice_number_increment = 1
    db = InvoiceDatabase(settings)
    assert db.peek_next_invoice_number() == "INV-00001"
    first, value = db.allocate_invoice_number()
    second, value2 = db.allocate_invoice_number()
    assert first == "INV-00001"
    assert value == 1
    assert second == "INV-00002"
    assert value2 == 2
    assert db.peek_next_invoice_number() == "INV-00003"


def test_emit_persists_invoice_in_sqlite(settings, signer):
    invoice = make_invoice(encf="E310000000077", dry_run=True)
    result = emit_invoice(invoice, settings, signer=signer)
    assert result.invoice_number.startswith("INV-")
    db = InvoiceDatabase(settings)
    loaded = db.load_result("E310000000077")
    assert loaded is not None
    assert loaded.invoice_number == result.invoice_number
    rows = db.list_invoices()
    assert any(row["encf"] == "E310000000077" for row in rows)
