"""Build DGII ConsultaTimbre / ConsultaTimbreFC QR URLs."""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlencode

from app.config import EnvironmentName, FC_BASE, ECF_BASE
from app.totals import format_money


def build_ecf_qr_url(
    *,
    env: EnvironmentName,
    rnc_emisor: str,
    rnc_comprador: str,
    encf: str,
    fecha_emision: str,
    monto_total: Decimal,
    fecha_firma: str,
    codigo_seguridad: str,
) -> str:
    base = f"{ECF_BASE[env]}/consultatimbre"
    query = urlencode(
        {
            "RncEmisor": rnc_emisor,
            "RncComprador": rnc_comprador,
            "ENCF": encf,
            "FechaEmision": fecha_emision,
            "MontoTotal": format_money(monto_total),
            "FechaFirma": fecha_firma,
            "CodigoSeguridad": codigo_seguridad,
        }
    )
    return f"{base}?{query}"


def build_fc_qr_url(
    *,
    env: EnvironmentName,
    rnc_emisor: str,
    encf: str,
    monto_total: Decimal,
    codigo_seguridad: str,
) -> str:
    base = f"{FC_BASE[env]}/consultatimbrefc"
    query = urlencode(
        {
            "RncEmisor": rnc_emisor,
            "ENCF": encf,
            "MontoTotal": format_money(monto_total),
            "CodigoSeguridad": codigo_seguridad,
        }
    )
    return f"{base}?{query}"
