"""FastAPI application exposing emit_invoice and a vanilla HTML UI."""

from __future__ import annotations

import io
from pathlib import Path

import qrcode
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.i18n import default_language, language_options, translations_for
from app.models import InvoiceInput, InvoiceResult
from app.service import InvoiceValidationError, emit_invoice, refresh_status
from app.storage import InvoiceStore
from app.totals import format_money

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"
FAVICON_DIR = TEMPLATES_DIR / "favicon_io"

app = FastAPI(title="DGII e-CF Issuer", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/icons", StaticFiles(directory=FAVICON_DIR), name="icons")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(FAVICON_DIR / "favicon.ico")


def _safe_settings() -> Settings | None:
    try:
        return get_settings()
    except Exception:
        return None


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


def _language_payload(codes: list[str]) -> dict:
    return {
        "available_languages": language_options(codes),
        "default_language": default_language(codes),
        "translations": translations_for(codes),
    }


@app.get("/api/config")
def public_config() -> dict:
    settings = _safe_settings()
    if settings is None:
        langs = ["en", "es"]
        return {
            "dgii_env": "testecf",
            "issuer_rnc": "",
            "issuer_name": "",
            "issuer_address": "",
            "configured": False,
            "next_invoice_number": None,
            "invoice_number_prefix": "INV-",
            **_language_payload(langs),
        }
    store = InvoiceStore(settings)
    return {
        "dgii_env": settings.dgii_env,
        "issuer_rnc": settings.issuer_rnc,
        "issuer_name": settings.issuer_name,
        "issuer_address": settings.issuer_address,
        "configured": settings.dgii_p12_path.exists(),
        "next_invoice_number": store.peek_next_invoice_number(),
        "invoice_number_prefix": settings.invoice_number_prefix,
        "invoice_number_start": settings.invoice_number_start,
        "invoice_number_increment": settings.invoice_number_increment,
        "invoice_number_digits": settings.invoice_number_digits,
        **_language_payload(settings.available_languages),
    }


@app.get("/api/invoices")
def list_invoices(limit: int = 50) -> dict:
    settings = _safe_settings()
    if settings is None:
        raise HTTPException(status_code=503, detail="Server is not configured.")
    limit = max(1, min(limit, 200))
    return {"items": InvoiceStore(settings).list_invoices(limit=limit)}


@app.post("/api/invoices", response_model=InvoiceResult)
def create_invoice(invoice: InvoiceInput) -> InvoiceResult:
    settings = _safe_settings()
    if settings is None and not invoice.dry_run:
        raise HTTPException(
            status_code=503,
            detail="Server is not configured. Set DGII_P12_PATH and related env vars.",
        )
    try:
        if settings is None:
            # dry_run without full settings still needs a p12 for signing in tests;
            # require settings always for signing path.
            raise HTTPException(status_code=503, detail="Server is not configured.")
        return emit_invoice(invoice, settings)
    except InvoiceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/invoices/{encf}", response_model=InvoiceResult)
def get_invoice(encf: str) -> InvoiceResult:
    settings = _safe_settings()
    if settings is None:
        raise HTTPException(status_code=503, detail="Server is not configured.")
    result = InvoiceStore(settings).load_result(encf)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Invoice {encf} not found")
    return result


@app.get("/api/invoices/{encf}/status", response_model=InvoiceResult)
def invoice_status(encf: str) -> InvoiceResult:
    settings = _safe_settings()
    if settings is None:
        raise HTTPException(status_code=503, detail="Server is not configured.")
    try:
        return refresh_status(encf, settings)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/invoices/{encf}/xml")
def download_xml(encf: str) -> FileResponse:
    settings = _safe_settings()
    if settings is None:
        raise HTTPException(status_code=503, detail="Server is not configured.")
    store = InvoiceStore(settings)
    result = store.load_result(encf)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Invoice {encf} not found")
    path = Path(result.xml_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Signed XML file is missing")
    return FileResponse(
        path,
        media_type="application/xml",
        filename=path.name,
    )


@app.get("/api/invoices/{encf}/qr.png")
def invoice_qr_png(encf: str) -> StreamingResponse:
    settings = _safe_settings()
    if settings is None:
        raise HTTPException(status_code=503, detail="Server is not configured.")
    result = InvoiceStore(settings).load_result(encf)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Invoice {encf} not found")
    image = qrcode.make(result.qr_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="image/png")


@app.get("/invoices/{encf}/print", response_class=HTMLResponse)
def print_invoice(request: Request, encf: str) -> HTMLResponse:
    settings = _safe_settings()
    if settings is None:
        raise HTTPException(status_code=503, detail="Server is not configured.")
    store = InvoiceStore(settings)
    result = store.load_result(encf)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Invoice {encf} not found")
    snapshot = result.print_snapshot
    return templates.TemplateResponse(
        request,
        "print.html",
        {
            "result": result,
            "snapshot": snapshot,
            "monto_total": format_money(result.monto_total),
        },
    )


@app.get("/health")
def health() -> dict:
    settings = _safe_settings()
    return {
        "status": "ok",
        "configured": settings is not None and settings.dgii_p12_path.exists(),
    }
