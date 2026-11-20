import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.config import get_settings
from tests.conftest import make_invoice


@pytest.fixture
def client(settings, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("DGII_ENV", settings.dgii_env)
    monkeypatch.setenv("DGII_P12_PATH", str(settings.dgii_p12_path))
    monkeypatch.setenv("DGII_P12_PASSWORD", settings.dgii_p12_password)
    monkeypatch.setenv("ISSUER_RNC", settings.issuer_rnc)
    monkeypatch.setenv("ISSUER_NAME", settings.issuer_name)
    monkeypatch.setenv("ISSUER_ADDRESS", settings.issuer_address)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_api_rejects_bad_encf(client):
    payload = make_invoice().model_dump(mode="json")
    payload["encf"] = "BAD"
    response = client.post("/api/invoices", json=payload)
    assert response.status_code == 422


def test_api_rejects_e31_without_buyer(client):
    payload = {
        "tipoe_cf": 31,
        "encf": "E310000000099",
        "fecha_vencimiento_secuencia": "2027-12-31",
        "issuer": {
            "rnc": "131880738",
            "name": "EMPRESA DE PRUEBA SRL",
            "address": "Av. Test #1",
        },
        "items": [
            {
                "name": "Servicio",
                "quantity": "1",
                "unit_price": "10",
                "good_or_service": 2,
                "tax_indicator": 1,
            }
        ],
        "dry_run": True,
    }
    response = client.post("/api/invoices", json=payload)
    assert response.status_code == 422


def test_api_dry_run_success(client):
    payload = make_invoice(encf="E310000000050", dry_run=True).model_dump(mode="json")
    response = client.post("/api/invoices", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["encf"] == "E310000000050"
    assert data["codigo_seguridad"]
    assert data["dry_run"] is True

    xml = client.get("/api/invoices/E310000000050/xml")
    assert xml.status_code == 200
    assert b"<ECF>" in xml.content

    qr = client.get("/api/invoices/E310000000050/qr.png")
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"

    printed = client.get("/invoices/E310000000050/print")
    assert printed.status_code == 200
    assert "E310000000050" in printed.text
