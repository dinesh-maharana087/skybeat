"""Validated, secret-safe runtime configuration."""

import re
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SKYBEAT_", extra="forbid", hide_input_in_errors=True
    )

    env: Literal["development", "test", "production"] = "production"
    database_url: SecretStr = Field(repr=False)
    public_base_url: str = "https://localhost"
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    enable_api_docs: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    db_pool_size: int = Field(default=5, ge=1, le=20)
    db_max_overflow: int = Field(default=5, ge=0, le=20)
    db_pool_timeout_seconds: int = Field(default=2, ge=1, le=10)
    db_connect_timeout_seconds: int = Field(default=3, ge=1, le=10)
    db_read_timeout_seconds: int = Field(default=3, ge=1, le=10)
    db_write_timeout_seconds: int = Field(default=3, ge=1, le=10)
    db_lock_timeout_seconds: int = Field(default=1, ge=1, le=3)
    db_select_timeout_ms: int = Field(default=3000, ge=100, le=10000)
    health_sweep_seconds: int = Field(default=5, ge=1, le=60)
    notification_poll_seconds: int = Field(default=5, ge=1, le=60)
    notification_concurrency: int = Field(default=4, ge=1, le=4)
    alert_email_recipients: Annotated[tuple[str, ...], NoDecode] = ()
    smtp_host: str | None = Field(default=None, min_length=1, max_length=253)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = Field(default=None, max_length=320)
    smtp_password: SecretStr | None = Field(default=None, repr=False)
    smtp_from_address: str | None = Field(default=None, max_length=320)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except (ArgumentError, ValueError):
            raise ValueError("A valid MySQL database URL is required.") from None
        if (
            url.drivername != "mysql+pymysql"
            or not url.host
            or not url.database
            or not url.username
            or url.username.lower() == "root"
            or not url.password
            or set(url.query) - {"charset"}
            or url.query.get("charset", "utf8mb4") != "utf8mb4"
        ):
            raise ValueError("Use mysql+pymysql with a scoped account and utf8mb4.")
        return value

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [host.strip() for host in value.split(",") if host.strip()]
        return value

    @field_validator("alert_email_recipients", mode="before")
    @classmethod
    def parse_alert_email_recipients(cls, value: object) -> object:
        values = value.split(",") if isinstance(value, str) else value
        if not isinstance(values, (list, tuple)):
            return values
        normalized = []
        for recipient in values:
            if not isinstance(recipient, str):
                raise ValueError("Alert recipients must be email addresses.")
            address = recipient.strip().lower()
            if not re.fullmatch(r"[^\s@\r\n]{1,64}@[^\s@\r\n]{1,255}", address):
                raise ValueError("Alert recipient is invalid.")
            normalized.append(address)
        return tuple(sorted(set(normalized)))

    @field_validator("smtp_host", "smtp_username", "smtp_from_address", mode="before")
    @classmethod
    def normalize_optional_smtp_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def validate_production(self) -> Self:
        try:
            url = urlsplit(self.public_base_url)
            valid_url = bool(url.hostname) and not url.username and not url.password
        except ValueError:
            valid_url = False
        if not valid_url or url.scheme not in {"https", "http"} or url.query or url.fragment:
            raise ValueError("Public base URL must be an origin without credentials or query.")
        if url.path not in {"", "/"}:
            raise ValueError("Public base URL must not contain a path.")
        if not self.allowed_hosts or any("*" in host for host in self.allowed_hosts):
            raise ValueError("An explicit host allowlist is required.")
        if self.env == "production":
            if url.scheme != "https" or url.hostname in {"localhost", "127.0.0.1", "testserver"}:
                raise ValueError("Production requires an explicit HTTPS origin.")
            if url.hostname not in self.allowed_hosts or self.enable_api_docs:
                raise ValueError("Production requires an allowed origin and disabled API docs.")
            if self.alert_email_recipients and (
                not self.smtp_host or not self.smtp_from_address or self.smtp_password is None
            ):
                raise ValueError(
                    "Production email recipients require protected SMTP configuration."
                )
        return self
