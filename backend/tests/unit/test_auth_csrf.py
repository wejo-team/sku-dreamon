"""CSRF 토큰의 위조 거부·세션 결합과 같은 상태의 토큰 재사용을 검증한다."""

import pytest

from app.core.exceptions import AppError
from app.domains.auth.csrf import (
    get_or_create_csrf_token,
    issue_csrf_token,
    validate_csrf_token,
)

SIGNING_KEY = "test-only-signing-key-with-at-least-32-bytes"
SESSION_HASH = b"a" * 32


def test_tokens_are_unpredictable_and_bound_to_the_current_authentication() -> None:
    anonymous = issue_csrf_token(SIGNING_KEY, None)
    signed_in = issue_csrf_token(SIGNING_KEY, SESSION_HASH)

    assert anonymous != issue_csrf_token(SIGNING_KEY, None)
    assert signed_in != issue_csrf_token(SIGNING_KEY, SESSION_HASH)
    assert validate_csrf_token(anonymous, SIGNING_KEY, None)
    assert validate_csrf_token(signed_in, SIGNING_KEY, SESSION_HASH)
    assert not validate_csrf_token(anonymous, SIGNING_KEY, SESSION_HASH)
    assert not validate_csrf_token(signed_in, SIGNING_KEY, None)
    assert not validate_csrf_token(signed_in, SIGNING_KEY, b"b" * 32)
    assert not validate_csrf_token(signed_in, "another-server-key", SESSION_HASH)
    assert SESSION_HASH.hex() not in signed_in


@pytest.mark.parametrize(
    "token",
    ["", "v1", "v2.fake.fake", "v1.한글.한글", "v1.!.!", "v1." + "A" * 10000],
)
def test_malformed_tokens_are_rejected(token: str) -> None:
    assert not validate_csrf_token(token, SIGNING_KEY, None)


def test_signature_and_nonce_tampering_are_rejected() -> None:
    token = issue_csrf_token(SIGNING_KEY, SESSION_HASH)
    version, nonce, signature = token.split(".")
    changed_nonce = ("A" if nonce[0] != "A" else "B") + nonce[1:]
    changed_signature = ("A" if signature[0] != "A" else "B") + signature[1:]

    assert not validate_csrf_token(
        f"{version}.{changed_nonce}.{signature}", SIGNING_KEY, SESSION_HASH
    )
    assert not validate_csrf_token(
        f"{version}.{nonce}.{changed_signature}", SIGNING_KEY, SESSION_HASH
    )


def test_existing_cookie_is_reused_only_for_the_same_valid_authentication() -> None:
    existing = issue_csrf_token(SIGNING_KEY, SESSION_HASH)

    assert get_or_create_csrf_token(existing, SIGNING_KEY, SESSION_HASH) == existing
    assert get_or_create_csrf_token(existing, SIGNING_KEY, None) != existing
    assert get_or_create_csrf_token(existing, SIGNING_KEY, b"b" * 32) != existing
    replacement = get_or_create_csrf_token("invalid", SIGNING_KEY, SESSION_HASH)
    assert validate_csrf_token(replacement, SIGNING_KEY, SESSION_HASH)
    first = get_or_create_csrf_token(None, SIGNING_KEY, None)
    assert validate_csrf_token(first, SIGNING_KEY, None)
    assert get_or_create_csrf_token(first, SIGNING_KEY, None) == first


def test_missing_signing_key_is_configuration_failure() -> None:
    with pytest.raises(AppError) as error:
        issue_csrf_token("", None)

    assert error.value.status_code == 503
    assert error.value.code == "TEMPORARY_UNAVAILABLE"
    with pytest.raises(AppError):
        validate_csrf_token("untrusted-token", "", None)
