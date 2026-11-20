"""SQLite persistence for invoices and invoice-number sequence."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from app.config import Settings
from app.models import InvoiceInput, InvoiceResult


def format_invoice_number(value: int, settings: Settings) -> str:
    width = settings.invoice_number_digits
    fmt = settings.invoice_number_format.strip()
    if fmt and set(fmt) <= {"0"}:
        width = max(width, len(fmt))
    return f"{settings.invoice_number_prefix}{value:0{width}d}"


class InvoiceDatabase:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.database_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS invoice_sequence (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    next_value INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_number TEXT NOT NULL UNIQUE,
                    sequence_value INTEGER NOT NULL,
                    encf TEXT NOT NULL UNIQUE,
                    tipoe_cf INTEGER NOT NULL,
                    monto_total TEXT NOT NULL,
                    estado TEXT,
                    dry_run INTEGER NOT NULL DEFAULT 0,
                    used_rfce INTEGER NOT NULL DEFAULT 0,
                    track_id TEXT,
                    codigo_seguridad TEXT,
                    qr_url TEXT,
                    xml_path TEXT,
                    sent_payload_path TEXT,
                    input_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_invoices_created_at
                    ON invoices (created_at DESC);
                """
            )
            row = conn.execute(
                "SELECT next_value FROM invoice_sequence WHERE id = 1"
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO invoice_sequence (id, next_value) VALUES (1, ?)",
                    (self.settings.invoice_number_start,),
                )

    def peek_next_invoice_number(self) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT next_value FROM invoice_sequence WHERE id = 1"
            ).fetchone()
            value = int(row["next_value"]) if row else self.settings.invoice_number_start
        return format_invoice_number(value, self.settings)

    def allocate_invoice_number(self) -> tuple[str, int]:
        """Reserve the next invoice number atomically."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT next_value FROM invoice_sequence WHERE id = 1"
            ).fetchone()
            if row is None:
                value = self.settings.invoice_number_start
                conn.execute(
                    "INSERT INTO invoice_sequence (id, next_value) VALUES (1, ?)",
                    (value + self.settings.invoice_number_increment,),
                )
            else:
                value = int(row["next_value"])
                conn.execute(
                    "UPDATE invoice_sequence SET next_value = ? WHERE id = 1",
                    (value + self.settings.invoice_number_increment,),
                )
            return format_invoice_number(value, self.settings), value

    def save_invoice(
        self,
        *,
        invoice_number: str,
        sequence_value: int,
        invoice: InvoiceInput,
        result: InvoiceResult,
    ) -> None:
        created_at = (
            result.created_at.isoformat()
            if isinstance(result.created_at, datetime)
            else str(result.created_at)
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO invoices (
                    invoice_number, sequence_value, encf, tipoe_cf, monto_total,
                    estado, dry_run, used_rfce, track_id, codigo_seguridad, qr_url,
                    xml_path, sent_payload_path, input_json, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(encf) DO UPDATE SET
                    invoice_number=excluded.invoice_number,
                    sequence_value=excluded.sequence_value,
                    tipoe_cf=excluded.tipoe_cf,
                    monto_total=excluded.monto_total,
                    estado=excluded.estado,
                    dry_run=excluded.dry_run,
                    used_rfce=excluded.used_rfce,
                    track_id=excluded.track_id,
                    codigo_seguridad=excluded.codigo_seguridad,
                    qr_url=excluded.qr_url,
                    xml_path=excluded.xml_path,
                    sent_payload_path=excluded.sent_payload_path,
                    input_json=excluded.input_json,
                    result_json=excluded.result_json,
                    created_at=excluded.created_at
                """,
                (
                    invoice_number,
                    sequence_value,
                    result.encf,
                    result.tipoe_cf,
                    str(result.monto_total),
                    result.estado,
                    1 if result.dry_run else 0,
                    1 if result.used_rfce else 0,
                    result.track_id,
                    result.codigo_seguridad,
                    result.qr_url,
                    result.xml_path,
                    result.sent_payload_path,
                    invoice.model_dump_json(),
                    result.model_dump_json(),
                    created_at,
                ),
            )

    def update_result(self, result: InvoiceResult) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE invoices SET
                    estado = ?,
                    track_id = ?,
                    result_json = ?,
                    codigo_seguridad = ?,
                    qr_url = ?,
                    sent_payload_path = ?
                WHERE encf = ?
                """,
                (
                    result.estado,
                    result.track_id,
                    result.model_dump_json(),
                    result.codigo_seguridad,
                    result.qr_url,
                    result.sent_payload_path,
                    result.encf,
                ),
            )

    def load_result(self, encf: str) -> InvoiceResult | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM invoices WHERE encf = ?",
                (encf.upper(),),
            ).fetchone()
        if row is None:
            return None
        return InvoiceResult.model_validate_json(row["result_json"])

    def load_result_by_invoice_number(self, invoice_number: str) -> InvoiceResult | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM invoices WHERE invoice_number = ?",
                (invoice_number,),
            ).fetchone()
        if row is None:
            return None
        return InvoiceResult.model_validate_json(row["result_json"])

    def list_invoices(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT invoice_number, encf, tipoe_cf, monto_total, estado,
                       dry_run, used_rfce, track_id, created_at
                FROM invoices
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
