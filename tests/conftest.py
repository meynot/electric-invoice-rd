"""Shared fixtures: self-signed .p12 and temporary settings."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
from cryptography.x509.oid import NameOID

from app.config import Settings
from app.models import InvoiceInput, LineItem, Party
from app.signer import Signer


@pytest.fixture
def p12_path(tmp_path: Path) -> Path:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "DO"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Emisor"),
            x509.NameAttribute(NameOID.COMMON_NAME, "131880738"),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, "131880738"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime.utcnow() - dt.timedelta(days=1))
        .not_valid_after(dt.datetime.utcnow() + dt.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    path = tmp_path / "test.p12"
    payload = pkcs12.serialize_key_and_certificates(
        name=b"test",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=BestAvailableEncryption(b"secret"),
    )
    path.write_bytes(payload)
    return path


@pytest.fixture
def settings(tmp_path: Path, p12_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return Settings(
        DGII_ENV="testecf",
        DGII_P12_PATH=p12_path,
        DGII_P12_PASSWORD="secret",
        ISSUER_RNC="131880738",
        ISSUER_NAME="EMPRESA DE PRUEBA SRL",
        ISSUER_ADDRESS="Av. Test #1, Santo Domingo",
        DATA_DIR=data_dir,
        DATABASE_PATH=str(data_dir / "invoices.db"),
        INVOICE_NUMBER_START=1,
        INVOICE_NUMBER_INCREMENT=1,
        INVOICE_NUMBER_PREFIX="INV-",
        INVOICE_NUMBER_DIGITS=5,
        INVOICE_NUMBER_FORMAT="00000",
    )


@pytest.fixture
def signer(settings: Settings) -> Signer:
    return Signer.from_p12(settings.dgii_p12_path, settings.dgii_p12_password)


@pytest.fixture
def issuer() -> Party:
    return Party(
        rnc="131880738",
        name="EMPRESA DE PRUEBA SRL",
        address="Av. Test #1, Santo Domingo",
    )


@pytest.fixture
def buyer() -> Party:
    return Party(
        rnc="101672919",
        name="CLIENTE DE PRUEBA SRL",
        address="Calle Cliente #10",
    )


def make_invoice(**overrides) -> InvoiceInput:
    base = {
        "tipoe_cf": 31,
        "encf": "E310000000001",
        "fecha_vencimiento_secuencia": dt.date(2027, 12, 31),
        "fecha_emision": dt.date(2026, 11, 19),
        "issuer": Party(
            rnc="131880738",
            name="EMPRESA DE PRUEBA SRL",
            address="Av. Test #1, Santo Domingo",
        ),
        "buyer": Party(
            rnc="101672919",
            name="CLIENTE DE PRUEBA SRL",
            address="Calle Cliente #10",
        ),
        "items": [
            LineItem(
                name="Servicio de prueba",
                quantity="1",
                unit_price="100.00",
                good_or_service=2,
                tax_indicator=1,
            )
        ],
        "dry_run": True,
    }
    base.update(overrides)
    return InvoiceInput(**base)
