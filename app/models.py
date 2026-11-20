"""Pydantic models for invoice input and emission results."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TaxIndicator = Literal[1, 2, 3, 4]
GoodOrService = Literal[1, 2]
InvoiceType = Literal[31, 32]
PaymentType = Literal[1, 2, 3]
IncomeType = Literal["01", "02", "03", "04", "05", "06"]

ENCF_RE = re.compile(r"^E(31|32)\d{10}$")
RNC_RE = re.compile(r"^\d{9}$|^\d{11}$")

RFCE_THRESHOLD = Decimal("250000.00")

ITBIS_RATES: dict[int, Decimal] = {
    1: Decimal("0.18"),
    2: Decimal("0.16"),
    3: Decimal("0.00"),
    4: Decimal("0.00"),
}


class Party(BaseModel):
    rnc: str
    name: str = Field(min_length=1, max_length=150)
    address: str | None = Field(default=None, max_length=100)

    @field_validator("rnc")
    @classmethod
    def validate_rnc(cls, value: str) -> str:
        cleaned = value.strip()
        if not RNC_RE.match(cleaned):
            raise ValueError("RNC must be 9 or 11 digits")
        return cleaned


class LineItem(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    good_or_service: GoodOrService = 1
    tax_indicator: TaxIndicator = 1
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("quantity", "unit_price", mode="before")
    @classmethod
    def to_decimal(cls, value: object) -> Decimal:
        return Decimal(str(value))


class InvoiceInput(BaseModel):
    tipoe_cf: InvoiceType
    encf: str
    fecha_vencimiento_secuencia: date | None = None
    issuer: Party
    buyer: Party | None = None
    tipo_ingresos: IncomeType = "01"
    tipo_pago: PaymentType = 1
    fecha_limite_pago: date | None = None
    fecha_emision: date | None = None
    items: list[LineItem] = Field(min_length=1)
    dry_run: bool = False

    @field_validator("encf")
    @classmethod
    def validate_encf(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not ENCF_RE.match(cleaned):
            raise ValueError("e-NCF must match E31 or E32 followed by 10 digits")
        return cleaned

    @model_validator(mode="after")
    def validate_consistency(self) -> InvoiceInput:
        expected_prefix = f"E{self.tipoe_cf}"
        if not self.encf.startswith(expected_prefix):
            raise ValueError(
                f"e-NCF {self.encf} does not match tipoe_cf {self.tipoe_cf}"
            )

        # Formato e-CF: FechaVencimientoSecuencia obligation is 1 for E31 and 0 for E32.
        if self.tipoe_cf == 32:
            self.fecha_vencimiento_secuencia = None
        elif self.fecha_vencimiento_secuencia is None:
            raise ValueError("fecha_vencimiento_secuencia is required for E31")
        if self.tipoe_cf == 31 and self.buyer is None:
            raise ValueError("buyer is required for E31")
        if not self.issuer.address:
            raise ValueError("issuer.address is required")

        # Formato e-CF: FechaLimitePago is required when TipoPago is credit (2).
        if self.tipo_pago == 2:
            if self.fecha_limite_pago is None:
                raise ValueError(
                    "fecha_limite_pago is required when tipo_pago is credit (2)"
                )
            emision = self.fecha_emision or date.today()
            if self.fecha_limite_pago < emision:
                raise ValueError("fecha_limite_pago must be >= fecha_emision")
        else:
            self.fecha_limite_pago = None

        return self


class InvoiceTotals(BaseModel):
    monto_gravado_i1: Decimal = Decimal("0.00")
    monto_gravado_i2: Decimal = Decimal("0.00")
    monto_gravado_i3: Decimal = Decimal("0.00")
    monto_exento: Decimal = Decimal("0.00")
    total_itbis_1: Decimal = Decimal("0.00")
    total_itbis_2: Decimal = Decimal("0.00")
    total_itbis_3: Decimal = Decimal("0.00")
    total_itbis: Decimal = Decimal("0.00")
    monto_gravado_total: Decimal = Decimal("0.00")
    monto_total: Decimal = Decimal("0.00")

    @property
    def uses_rfce(self) -> bool:
        return self.monto_total < RFCE_THRESHOLD


class PrintLine(BaseModel):
    numero: int
    name: str
    quantity: str
    unit_price: str
    amount: str
    tax_indicator: int


class PrintSnapshot(BaseModel):
    issuer_rnc: str
    issuer_name: str
    issuer_address: str
    buyer_rnc: str | None = None
    buyer_name: str | None = None
    fecha_emision: str
    fecha_vencimiento: str | None = None
    lines: list[PrintLine]
    monto_gravado_total: str
    total_itbis: str
    monto_exento: str
    monto_total: str


class InvoiceResult(BaseModel):
    invoice_number: str
    encf: str
    tipoe_cf: InvoiceType
    monto_total: Decimal
    used_rfce: bool
    codigo_seguridad: str
    qr_url: str
    fecha_firma: str
    xml_path: str
    sent_payload_path: str | None = None
    track_id: str | None = None
    estado: str | None = None
    mensajes: list[str] = Field(default_factory=list)
    error: str | None = None
    secuencia_utilizada: bool | None = None
    dry_run: bool = False
    print_snapshot: PrintSnapshot | None = None
    created_at: datetime = Field(default_factory=datetime.now)
