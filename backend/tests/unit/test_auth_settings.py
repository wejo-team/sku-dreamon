"""CSRF 키와 허용 origin의 안전한 설정 경계를 검증한다."""

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def test_auth_settings_keep_secret_hidden_and_normalize_https_origins() -> None:
    key = "development-test-key-32-bytes-minimum"
    settings = Settings(
        csrf_signing_key=SecretStr(key),
        auth_allowed_origins=("https://APP.example.com:443/", "https://localhost:5173"),
        _env_file=None,
    )
    assert key not in repr(settings)
    assert settings.auth_allowed_origins == (
        "https://app.example.com",
        "https://localhost:5173",
    )


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "http://example.com",
        "https://*.example.com",
        "https://user:password@example.com",
        "https://example.com/path",
        "https://example.com?query=1",
        "https://example.com#fragment",
    ],
)
def test_auth_settings_reject_unusable_or_overbroad_origins(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(auth_allowed_origins=(origin,), _env_file=None)


def test_auth_settings_reject_a_short_hmac_key() -> None:
    with pytest.raises(ValidationError):
        Settings(csrf_signing_key=SecretStr("too-short"), _env_file=None)
