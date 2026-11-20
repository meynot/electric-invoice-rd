"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.i18n import normalize_languages

EnvironmentName = Literal["testecf", "certecf", "ecf"]

ECF_BASE = {
    "testecf": "https://ecf.dgii.gov.do/testecf",
    "certecf": "https://ecf.dgii.gov.do/certecf",
    "ecf": "https://ecf.dgii.gov.do/ecf",
}

FC_BASE = {
    "testecf": "https://fc.dgii.gov.do/testecf",
    "certecf": "https://fc.dgii.gov.do/certecf",
    "ecf": "https://fc.dgii.gov.do/ecf",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    dgii_env: EnvironmentName = Field(default="testecf", alias="DGII_ENV")
    dgii_p12_path: Path = Field(alias="DGII_P12_PATH")
    dgii_p12_password: str = Field(alias="DGII_P12_PASSWORD")
    issuer_rnc: str = Field(alias="ISSUER_RNC")
    issuer_name: str = Field(alias="ISSUER_NAME")
    issuer_address: str = Field(alias="ISSUER_ADDRESS")
    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    available_languages_raw: str = Field(
        default="en,es",
        alias="AVAILABLE_LANGUAGES",
    )
    invoice_number_start: int = Field(default=1, alias="INVOICE_NUMBER_START")
    invoice_number_increment: int = Field(default=1, alias="INVOICE_NUMBER_INCREMENT")
    invoice_number_digits: int = Field(default=5, alias="INVOICE_NUMBER_DIGITS")
    invoice_number_format: str = Field(default="00000", alias="INVOICE_NUMBER_FORMAT")
    invoice_number_prefix: str = Field(default="INV-", alias="INVOICE_NUMBER_PREFIX")
    database_path_raw: str | None = Field(default=None, alias="DATABASE_PATH")

    @property
    def available_languages(self) -> list[str]:
        return normalize_languages(self.available_languages_raw.split(","))

    @property
    def ecf_base_url(self) -> str:
        return ECF_BASE[self.dgii_env]

    @property
    def fc_base_url(self) -> str:
        return FC_BASE[self.dgii_env]

    @property
    def xml_dir(self) -> Path:
        path = self.data_dir / "xml"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def database_path(self) -> Path:
        if self.database_path_raw:
            return Path(self.database_path_raw)
        path = self.data_dir / "invoices.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
