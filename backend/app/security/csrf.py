"""현재 인증 결합에 대한 CSRF 서명·검증을 HTTP 없이 계산한다."""

import base64
import hashlib
import hmac
import re
import secrets

from app.core.exceptions import AppError

_TOKEN_PATTERN = re.compile(r"v1\.([A-Za-z0-9_-]{43})\.([A-Za-z0-9_-]{43})")


def require_signing_key(key: str) -> bytes:
    if not key:
        raise AppError(
            503, "TEMPORARY_UNAVAILABLE", "인증 서비스를 일시적으로 이용할 수 없습니다."
        )
    return key.encode("utf-8")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _signature(key: bytes, nonce: bytes, session_hash: bytes | None) -> bytes:
    # 버전·인증 상태를 분리하여 익명 토큰과 로그인 토큰을 서로 교환하지 못한다.
    if session_hash is None:
        binding = b"anonymous\x00"
    else:
        if len(session_hash) != 32:
            raise ValueError("session hash must contain 32 bytes")
        binding = b"authenticated\x00" + session_hash
    message = b"sku-dreamon-csrf-v1\x00" + binding + nonce
    return hmac.digest(key, message, hashlib.sha256)


def issue_csrf_token(key: str, session_hash: bytes | None) -> str:
    """세션 원문·해시를 포함하지 않는 새 nonce와 서명만 반환한다."""
    signing_key = require_signing_key(key)
    nonce = secrets.token_bytes(32)
    signature = _signature(signing_key, nonce, session_hash)
    return f"v1.{_encode(nonce)}.{_encode(signature)}"


def validate_csrf_token(token: str, key: str, session_hash: bytes | None) -> bool:
    """형식과 서명·현재 인증 결합을 확인하며 원문을 오류에 포함하지 않는다."""
    signing_key = require_signing_key(key)
    match = _TOKEN_PATTERN.fullmatch(token)
    if match is None:
        return False
    encoded_nonce, encoded_signature = match.groups()
    nonce = base64.urlsafe_b64decode(encoded_nonce + "=")
    signature = base64.urlsafe_b64decode(encoded_signature + "=")
    # 같은 바이트를 나타내는 비정규 base64 표기를 허용하지 않는다.
    if _encode(nonce) != encoded_nonce or _encode(signature) != encoded_signature:
        return False
    return hmac.compare_digest(signature, _signature(signing_key, nonce, session_hash))


def get_or_create_csrf_token(
    existing: str | None, key: str, session_hash: bytes | None
) -> str:
    """다른 탭의 조회로 쿠키가 바뀌지 않도록 같은 상태의 유효 값을 재사용한다."""
    if existing is not None and validate_csrf_token(existing, key, session_hash):
        return existing
    return issue_csrf_token(key, session_hash)
