"""HTTP client for DGII authentication, reception, and status queries."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.config import Settings
from app.signer import Signer


@dataclass
class AuthToken:
    token: str
    expira: datetime | None = None
    expedido: datetime | None = None

    @property
    def is_expired(self) -> bool:
        if self.expira is None:
            return False
        # Refresh one minute early.
        return datetime.now(self.expira.tzinfo) >= self.expira


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


class DgiiClient:
    def __init__(
        self,
        settings: Settings,
        signer: Signer,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.signer = signer
        self._client = client or httpx.Client(timeout=60.0)
        self._owns_client = client is None
        self._token: AuthToken | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> DgiiClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def authenticate(self, *, force: bool = False) -> AuthToken:
        if self._token is not None and not force and not self._token.is_expired:
            return self._token

        seed_url = (
            f"{self.settings.ecf_base_url}/autenticacion/api/autenticacion/semilla"
        )
        seed_response = self._client.get(seed_url, headers={"Accept": "*/*"})
        seed_response.raise_for_status()
        seed_xml = seed_response.text
        signed_seed = self.signer.sign_xml(seed_xml)

        validate_url = (
            f"{self.settings.ecf_base_url}/autenticacion/api/autenticacion/validarsemilla"
        )
        files = {"xml": ("semilla.xml", signed_seed.encode("utf-8"), "text/xml")}
        token_response = self._client.post(
            validate_url,
            files=files,
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        payload = token_response.json()
        self._token = AuthToken(
            token=payload["token"],
            expira=_parse_dt(payload.get("expira")),
            expedido=_parse_dt(payload.get("expedido")),
        )
        return self._token

    def _auth_headers(self) -> dict[str, str]:
        token = self.authenticate()
        return {
            "Authorization": f"Bearer {token.token}",
            "Accept": "application/json",
        }

    def send_ecf(self, signed_xml: str, filename: str) -> dict[str, Any]:
        url = f"{self.settings.ecf_base_url}/recepcion/api/facturaselectronicas"
        files = {"xml": (filename, signed_xml.encode("utf-8"), "text/xml")}
        response = self._client.post(url, files=files, headers=self._auth_headers())
        response.raise_for_status()
        return response.json()

    def send_rfce(self, signed_xml: str, filename: str) -> dict[str, Any]:
        url = f"{self.settings.fc_base_url}/recepcionfc/api/recepcion/ecf"
        files = {"xml": (filename, signed_xml.encode("utf-8"), "text/xml")}
        response = self._client.post(url, files=files, headers=self._auth_headers())
        response.raise_for_status()
        return response.json()

    def track_status(self, track_id: str) -> dict[str, Any]:
        url = (
            f"{self.settings.ecf_base_url}/consultaresultado/api/consultas/estado"
        )
        response = self._client.get(
            url,
            params={"TrackId": track_id},
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    def poll_track_status(
        self,
        track_id: str,
        *,
        attempts: int = 8,
        delay_seconds: float = 1.5,
    ) -> dict[str, Any]:
        last: dict[str, Any] = {}
        for index in range(attempts):
            last = self.track_status(track_id)
            estado = str(last.get("estado") or last.get("Estado") or "").lower()
            if estado and estado not in {"en proceso", "en proceso", "recibido"}:
                return last
            if index < attempts - 1:
                time.sleep(delay_seconds)
        return last
