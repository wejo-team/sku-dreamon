"""환경설정을 읽고 비동기 PostgreSQL 연결에 필요한 값을 검증한다."""

from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    Field,
    HttpUrl,
    PostgresDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://wejo:wejo@127.0.0.1:5432/wejo_dev"),
        repr=False,
    )
    database_tls_ca_file: Path | None = None
    database_pool_size: int = Field(default=3, ge=1, le=30)
    database_max_overflow: int = Field(default=2, ge=0, le=30)
    database_pool_timeout_seconds: float = Field(default=3, ge=0.1, le=30)
    database_connect_timeout_seconds: float = Field(default=3, ge=0.1, le=30)
    database_command_timeout_seconds: float = Field(default=10, ge=0.1, le=60)
    database_statement_timeout_seconds: float = Field(default=10, ge=0.1, le=60)
    database_lock_timeout_seconds: float = Field(default=2, ge=0.1, le=30)
    database_idle_transaction_timeout_seconds: float = Field(default=15, ge=1, le=60)
    readiness_timeout_seconds: float = Field(default=3, ge=0.1, le=10)
    shutdown_timeout_seconds: float = Field(default=10, ge=0.1, le=30)
    http_allowed_hosts: tuple[str, ...] = ()
    http_trusted_proxies: tuple[str, ...] = ()
    openai_api_key: SecretStr | None = Field(default=None, repr=False)
    ai_required: bool = False
    ai_model: Literal["gpt-6-luna"] = "gpt-6-luna"
    ai_reasoning_effort: Literal["low", "medium", "high"] = "low"
    ai_timeout_seconds: int = Field(default=90, ge=10, le=300)
    ai_cleanup_timeout_seconds: float = Field(default=5, ge=0.1, le=30)
    ai_retention_seconds: int = Field(default=86400, ge=3600, le=604800)
    ai_max_output_tokens: int = Field(default=4096, ge=256, le=8192)
    ai_max_input_tokens: int = Field(default=18000, ge=1000, le=50000)
    ai_max_tool_calls: int = Field(default=8, ge=1, le=20)
    ai_max_sources: int = Field(default=30, ge=3, le=100)
    ai_requests_per_hour: int = Field(default=30, ge=1, le=300)
    ai_concurrent_requests: int = Field(default=2, ge=1, le=10)
    csrf_signing_key: SecretStr | None = None
    auth_allowed_origins: tuple[str, ...] = ()
    password_blocklist_path: Path | None = None
    password_blocklist_version: str = ""
    auth_login_account_limit: int = Field(default=10, ge=1)
    auth_login_ip_limit: int = Field(default=100, ge=1)
    auth_signup_ip_limit: int = Field(default=10, ge=1)
    auth_availability_ip_limit: int = Field(default=100, ge=1)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.get_secret_value())

    @field_validator("http_allowed_hosts")
    @classmethod
    def require_exact_hosts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            parsed = urlsplit(f"https://{value}")
            if (
                not value
                or parsed.hostname != value.lower()
                or parsed.netloc != value
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in value
                or any(character.isspace() for character in value)
            ):
                raise ValueError("Allowed hosts must be exact hostnames")
        return tuple(value.lower() for value in values)

    @field_validator("http_trusted_proxies")
    @classmethod
    def require_narrow_proxies(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            network = ip_network(value)
            minimum_prefix = 24 if network.version == 4 else 64
            if (
                network.prefixlen < minimum_prefix
                or network.is_unspecified
                or network.is_multicast
            ):
                raise ValueError("Trusted proxies require precise IPs or narrow CIDRs")
        return values

    @model_validator(mode="after")
    def require_production_settings(self) -> "Settings":
        if self.ai_required and not self.ai_enabled:
            raise ValueError("AI_REQUIRED requires a configured runtime API key")
        if self.app_env != "production":
            return self
        hosts = self.database_url.hosts()
        local_database = False
        for host in hosts:
            name = (host["host"] or "").lower().rstrip(".").strip("[]")
            if name == "localhost":
                local_database = True
            try:
                address = ip_address(name)
                local_database = (
                    local_database or address.is_loopback or address.is_unspecified
                )
            except ValueError:
                pass
        if (
            not self.database_tls_ca_file
            or "database_url" not in self.model_fields_set
            or len(hosts) != 1
            or local_database
        ):
            raise ValueError(
                "Required production database URL and verified TLS settings missing"
            )
        return self

    def require_http_configuration(self) -> None:
        """별도 DDL·배치 계정에는 요구하지 않는 운영 웹 보안 설정을 검사한다."""
        if self.app_env == "production" and (
            self.csrf_signing_key is None
            or not self.auth_allowed_origins
            or not self.password_blocklist_path
            or not self.password_blocklist_version.strip()
            or not self.http_allowed_hosts
            or not self.http_trusted_proxies
        ):
            raise ValueError("Required production HTTP security settings missing")

    @field_validator("csrf_signing_key")
    @classmethod
    def require_signing_key_length(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("CSRF signing key must contain at least 32 bytes")
        return value

    @field_validator("auth_allowed_origins")
    @classmethod
    def require_https_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        origins: list[str] = []
        for value in values:
            parsed = HttpUrl(value)
            if (
                parsed.scheme != "https"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in (None, "", "/")
                or parsed.query is not None
                or parsed.fragment is not None
                or "*" in value
            ):
                raise ValueError("Authentication origins must be exact HTTPS origins")
            origins.append(str(parsed).removesuffix("/"))
        return tuple(origins)

    @field_validator("database_url")
    @classmethod
    def require_asyncpg(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+asyncpg":
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg driver")
        if value.query:
            raise ValueError(
                "DATABASE_URL query options are forbidden; use DB settings"
            )
        return value
