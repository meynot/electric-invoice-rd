"""Persist signed XML on disk and invoice records in SQLite."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.db import InvoiceDatabase
from app.models import InvoiceInput, InvoiceResult


class InvoiceStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.xml_dir = settings.xml_dir
        self.db = InvoiceDatabase(settings)

    def xml_path(self, rnc: str, encf: str, *, suffix: str = "") -> Path:
        name = f"{rnc}{encf}{suffix}.xml"
        return self.xml_dir / name

    def save_xml(self, path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def allocate_invoice_number(self) -> tuple[str, int]:
        return self.db.allocate_invoice_number()

    def peek_next_invoice_number(self) -> str:
        return self.db.peek_next_invoice_number()

    def save_result(
        self,
        result: InvoiceResult,
        *,
        invoice: InvoiceInput | None = None,
        sequence_value: int | None = None,
    ) -> None:
        if invoice is not None and sequence_value is not None:
            self.db.save_invoice(
                invoice_number=result.invoice_number,
                sequence_value=sequence_value,
                invoice=invoice,
                result=result,
            )
        else:
            self.db.update_result(result)

    def load_result(self, encf: str) -> InvoiceResult | None:
        return self.db.load_result(encf)

    def load_xml(self, encf: str) -> str | None:
        result = self.load_result(encf)
        if result is None:
            return None
        path = Path(result.xml_path)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def list_invoices(self, *, limit: int = 50) -> list[dict]:
        return self.db.list_invoices(limit=limit)
