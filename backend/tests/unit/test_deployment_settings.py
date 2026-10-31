"""운영 설정 누락과 느슨한 신뢰 경계가 기동 전에 거부되는지 확인한다."""

from pathlib import Path

import pytest
from pydantic import PostgresDsn, SecretStr, ValidationError

from app.core.config import Settings


def test_production_rejects_development_defaults() -> None:
    with pytest.raises(ValidationError, match="production"):
        Settings(app_env="production", _env_file=None)


def test_database_credentials_are_not_in_settings_repr() -> None:
    settings = Settings(
        database_url=PostgresDsn(
            "postgresql+asyncpg://synthetic:synthetic-db-password@db.example.com/app"
        ),
        _env_file=None,
    )
    assert "synthetic-db-password" not in repr(settings)


@pytest.mark.parametrize("value", [0, -1, float("inf"), 31])
def test_ai_cleanup_has_a_finite_positive_budget(value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(ai_cleanup_timeout_seconds=value, _env_file=None)


@pytest.mark.parametrize("value", ["*", "0.0.0.0/0", "::/0", "10.0.0.0/8"])
def test_proxy_trust_cannot_be_wildcard_or_a_broad_network(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(http_trusted_proxies=(value,), _env_file=None)


@pytest.mark.parametrize("value", ["*", "*.example.com", "https://api.example.com"])
def test_hosts_are_exact_hostnames(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(http_allowed_hosts=(value,), _env_file=None)


@pytest.mark.parametrize("query", ["ssl=disable", "timeout=0", "server_settings=x"])
def test_database_query_parameters_cannot_override_connection_policy(
    query: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url=PostgresDsn(
                f"postgresql+asyncpg://synthetic:synthetic@db.example.com/app?{query}"
            ),
            _env_file=None,
        )


@pytest.mark.parametrize("key", [None, ""])
def test_required_ai_cannot_silently_disable_itself(key: str | None) -> None:
    with pytest.raises(ValidationError, match="AI_REQUIRED"):
        Settings(
            ai_required=True,
            openai_api_key=SecretStr(key) if key is not None else None,
            _env_file=None,
        )


def production_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="production",
        openai_api_key=None,
        langsmith_api_key=None,
        database_url=PostgresDsn(
            "postgresql+asyncpg://synthetic:synthetic@postgres/app"
        ),
        database_tls_ca_file=tmp_path / "synthetic-ca.pem",
        csrf_signing_key=SecretStr("synthetic-production-test-key-at-least-32-bytes"),
        auth_allowed_origins=("https://www.example.com",),
        password_blocklist_path=tmp_path / "synthetic-list.txt",
        password_blocklist_version="synthetic-v1",
        http_allowed_hosts=("api.example.com",),
        http_trusted_proxies=("192.0.2.10",),
        _env_file=None,
    )


def test_production_accepts_generic_postgresql_with_own_ca(tmp_path: Path) -> None:
    assert production_settings(tmp_path).app_env == "production"


@pytest.mark.parametrize("key", [None, "", " \t "])
def test_production_ai_can_start_without_langsmith_key(
    tmp_path: Path, key: str | None
) -> None:
    settings = production_settings(tmp_path).model_dump()
    settings.update(
        openai_api_key=SecretStr("synthetic-openai-key"),
        langsmith_api_key=SecretStr(key) if key is not None else None,
        ai_required=True,
    )
    config = Settings(_env_file=None, **settings)
    assert config.ai_enabled
    assert config.langsmith_api_key is None


def test_production_ai_accepts_langsmith_key_without_enable_flag(
    tmp_path: Path,
) -> None:
    settings = production_settings(tmp_path).model_dump()
    settings.update(
        openai_api_key=SecretStr("synthetic-openai-key"),
        langsmith_api_key=SecretStr("synthetic-tracing-key"),
    )
    assert Settings(_env_file=None, **settings).ai_enabled


@pytest.mark.parametrize(
    "host", ["127.9.8.7", "0.0.0.0", "[::]", "[::1]", "LOCALHOST."]
)
def test_production_rejects_all_loopback_and_unspecified_database_hosts(
    tmp_path: Path, host: str
) -> None:
    settings = production_settings(tmp_path).model_dump()
    settings["database_url"] = f"postgresql+asyncpg://synthetic:synthetic@{host}/app"
    with pytest.raises(ValueError, match="production"):
        Settings(_env_file=None, **settings).require_http_configuration()


def test_production_database_jobs_do_not_need_http_secrets(tmp_path: Path) -> None:
    settings = Settings(
        app_env="production",
        openai_api_key=None,
        langsmith_api_key=None,
        database_url=PostgresDsn(
            "postgresql+asyncpg://synthetic:synthetic@postgres/app"
        ),
        database_tls_ca_file=tmp_path / "synthetic-ca.pem",
        _env_file=None,
    )
    assert settings.csrf_signing_key is None
    assert settings.http_trusted_proxies == ()
    assert settings.langsmith_api_key is None
    assert not settings.ai_enabled
    with pytest.raises(ValueError, match="production HTTP"):
        settings.require_http_configuration()


@pytest.mark.parametrize(
    "field",
    [
        "database_tls_ca_file",
        "csrf_signing_key",
        "auth_allowed_origins",
        "password_blocklist_path",
        "password_blocklist_version",
        "http_allowed_hosts",
        "http_trusted_proxies",
    ],
)
def test_production_requires_each_security_boundary(tmp_path: Path, field: str) -> None:
    settings = production_settings(tmp_path).model_dump()
    del settings[field]
    with pytest.raises(ValueError, match="production"):
        Settings(_env_file=None, **settings).require_http_configuration()
