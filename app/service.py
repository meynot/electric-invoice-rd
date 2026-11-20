"""Callable emit_invoice orchestration for E31 and E32."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings, get_settings
from app.dgii_client import DgiiClient
from app.models import (
    RFCE_THRESHOLD,
    InvoiceInput,
    InvoiceResult,
    PrintLine,
    PrintSnapshot,
)
from app.qr import build_ecf_qr_url, build_fc_qr_url
from app.signer import Signer, extract_security_code
from app.storage import InvoiceStore
from app.totals import (
    compute_totals,
    format_money,
    format_quantity,
    format_unit_price,
    line_amount,
)
from app.xml_builder import (
    build_ecf_xml,
    build_rfce_xml,
    format_date,
    format_datetime,
    now_dr,
)


class InvoiceValidationError(ValueError):
    """Raised when business rules fail after totals are known."""


def _messages_from_payload(payload: dict) -> list[str]:
    messages: list[str] = []
    raw = payload.get("mensajes") or payload.get("Mensajes") or []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                code = item.get("codigo") or item.get("Codigo") or ""
                value = item.get("valor") or item.get("Valor") or item.get("mensaje") or ""
                text = f"{code}: {value}".strip(": ").strip()
                if text:
                    messages.append(text)
            elif item:
                messages.append(str(item))
    error = payload.get("error") or payload.get("Error")
    if error:
        messages.append(str(error))
    mensaje = payload.get("mensaje") or payload.get("Mensaje")
    if mensaje:
        messages.append(str(mensaje))
    return messages


def emit_invoice(
    invoice: InvoiceInput,
    settings: Settings | None = None,
    *,
    signer: Signer | None = None,
    client: DgiiClient | None = None,
) -> InvoiceResult:
    """Build, sign, and submit an E31/E32 electronic invoice to DGII.

    Set ``invoice.dry_run=True`` to stop after signing (no DGII network calls).
    """
    cfg = settings or get_settings()
    totals = compute_totals(invoice)

    if invoice.tipoe_cf == 32 and totals.monto_total >= RFCE_THRESHOLD and invoice.buyer is None:
        raise InvoiceValidationError(
            "buyer is required for E32 when MontoTotal is at least RD$250,000.00"
        )

    use_rfce = invoice.tipoe_cf == 32 and totals.monto_total < RFCE_THRESHOLD
    fecha_firma_dt = now_dr()
    fecha_firma = format_datetime(fecha_firma_dt)
    fecha_emision = format_date(invoice.fecha_emision or fecha_firma_dt.date())

    unsigned = build_ecf_xml(invoice, totals, fecha_firma=fecha_firma_dt)
    active_signer = signer or Signer.from_p12(cfg.dgii_p12_path, cfg.dgii_p12_password)
    signed_ecf = active_signer.sign_xml(unsigned)
    codigo = extract_security_code(signed_ecf)

    store = InvoiceStore(cfg)
    invoice_number, sequence_value = store.allocate_invoice_number()
    xml_path = store.save_xml(
        store.xml_path(invoice.issuer.rnc, invoice.encf),
        signed_ecf,
    )

    sent_payload_path: Path | None = None
    track_id: str | None = None
    estado: str | None = None
    mensajes: list[str] = []
    error: str | None = None
    secuencia_utilizada: bool | None = None

    if use_rfce:
        qr_url = build_fc_qr_url(
            env=cfg.dgii_env,
            rnc_emisor=invoice.issuer.rnc,
            encf=invoice.encf,
            monto_total=totals.monto_total,
            codigo_seguridad=codigo,
        )
    else:
        qr_url = build_ecf_qr_url(
            env=cfg.dgii_env,
            rnc_emisor=invoice.issuer.rnc,
            rnc_comprador=invoice.buyer.rnc if invoice.buyer else "",
            encf=invoice.encf,
            fecha_emision=fecha_emision,
            monto_total=totals.monto_total,
            fecha_firma=fecha_firma,
            codigo_seguridad=codigo,
        )

    if not invoice.dry_run:
        owns_client = client is None
        dgii = client or DgiiClient(cfg, active_signer)
        try:
            filename = f"{invoice.issuer.rnc}{invoice.encf}.xml"
            if use_rfce:
                rfce_unsigned = build_rfce_xml(invoice, totals, codigo)
                signed_rfce = active_signer.sign_xml(rfce_unsigned)
                sent_payload_path = store.save_xml(
                    store.xml_path(invoice.issuer.rnc, invoice.encf, suffix="_RFCE"),
                    signed_rfce,
                )
                payload = dgii.send_rfce(signed_rfce, filename)
                estado = str(payload.get("estado") or payload.get("Estado") or "")
                secuencia_utilizada = payload.get("secuenciaUtilizada")
                if secuencia_utilizada is None:
                    secuencia_utilizada = payload.get("SecuenciaUtilizada")
                mensajes = _messages_from_payload(payload)
                error = payload.get("error") or payload.get("Error")
            else:
                payload = dgii.send_ecf(signed_ecf, filename)
                track_id = payload.get("trackId") or payload.get("TrackId")
                error = payload.get("error") or payload.get("Error")
                mensajes = _messages_from_payload(payload)
                if track_id and not error:
                    status = dgii.poll_track_status(str(track_id))
                    estado = str(
                        status.get("estado")
                        or status.get("Estado")
                        or status.get("estadoEcf")
                        or ""
                    )
                    mensajes.extend(_messages_from_payload(status))
                else:
                    estado = "Error" if error else "Enviado"
        finally:
            if owns_client:
                dgii.close()
    else:
        if use_rfce:
            rfce_unsigned = build_rfce_xml(invoice, totals, codigo)
            signed_rfce = active_signer.sign_xml(rfce_unsigned)
            sent_payload_path = store.save_xml(
                store.xml_path(invoice.issuer.rnc, invoice.encf, suffix="_RFCE"),
                signed_rfce,
            )
        estado = "DryRun"

    snapshot = PrintSnapshot(
        issuer_rnc=invoice.issuer.rnc,
        issuer_name=invoice.issuer.name,
        issuer_address=invoice.issuer.address or "",
        buyer_rnc=invoice.buyer.rnc if invoice.buyer else None,
        buyer_name=invoice.buyer.name if invoice.buyer else None,
        fecha_emision=fecha_emision,
        fecha_vencimiento=(
            format_date(invoice.fecha_vencimiento_secuencia)
            if invoice.fecha_vencimiento_secuencia
            else None
        ),
        lines=[
            PrintLine(
                numero=index,
                name=item.name,
                quantity=format_quantity(item.quantity),
                unit_price=format_unit_price(item.unit_price),
                amount=format_money(line_amount(item)),
                tax_indicator=item.tax_indicator,
            )
            for index, item in enumerate(invoice.items, start=1)
        ],
        monto_gravado_total=format_money(totals.monto_gravado_total),
        total_itbis=format_money(totals.total_itbis),
        monto_exento=format_money(totals.monto_exento),
        monto_total=format_money(totals.monto_total),
    )

    result = InvoiceResult(
        invoice_number=invoice_number,
        encf=invoice.encf,
        tipoe_cf=invoice.tipoe_cf,
        monto_total=totals.monto_total,
        used_rfce=use_rfce,
        codigo_seguridad=codigo,
        qr_url=qr_url,
        fecha_firma=fecha_firma,
        xml_path=str(xml_path),
        sent_payload_path=str(sent_payload_path) if sent_payload_path else None,
        track_id=str(track_id) if track_id else None,
        estado=estado,
        mensajes=mensajes,
        error=str(error) if error else None,
        secuencia_utilizada=secuencia_utilizada,
        dry_run=invoice.dry_run,
        print_snapshot=snapshot,
    )
    store.save_result(result, invoice=invoice, sequence_value=sequence_value)
    return result


def refresh_status(
    encf: str,
    settings: Settings | None = None,
    *,
    signer: Signer | None = None,
    client: DgiiClient | None = None,
) -> InvoiceResult:
    """Re-poll DGII for a previously submitted full ECF by trackId."""
    cfg = settings or get_settings()
    store = InvoiceStore(cfg)
    existing = store.load_result(encf)
    if existing is None:
        raise FileNotFoundError(f"No stored invoice for {encf}")
    if not existing.track_id:
        return existing

    active_signer = signer or Signer.from_p12(cfg.dgii_p12_path, cfg.dgii_p12_password)
    owns_client = client is None
    dgii = client or DgiiClient(cfg, active_signer)
    try:
        status = dgii.track_status(existing.track_id)
    finally:
        if owns_client:
            dgii.close()

    existing.estado = str(
        status.get("estado") or status.get("Estado") or existing.estado or ""
    )
    existing.mensajes = _messages_from_payload(status) or existing.mensajes
    store.save_result(existing)
    return existing
