"""환경설정을 읽고 비동기 PostgreSQL 연결에 필요한 값을 검증한다."""

from pydantic import HttpUrl, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://wejo:wejo@127.0.0.1:5432/wejo"
    )
    csrf_signing_key: SecretStr | None = None
    auth_allowed_origins: tuple[str, ...] = ()

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
        return value
