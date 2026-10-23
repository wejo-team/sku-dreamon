"""로그인 전후의 서명된 CSRF 토큰과 상태 변경 요청의 출처를 검증한다."""

import base64
import hashlib
import hmac
import re
import secrets
from typing import Annotated, cast
from urllib.parse import urlsplit

from fastapi import Depends, Request

from app.core.config import Settings
from app.core.exceptions import AppError
from app.domains.auth.dependencies import get_optional_session
from app.domains.auth.session_service import SessionPrincipal

CSRF_COOKIE_NAME = "__Host-sku-dreamon-csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
_TOKEN_PATTERN = re.compile(r"v1\.([A-Za-z0-9_-]{43})\.([A-Za-z0-9_-]{43})")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _signing_key(key: str) -> bytes:
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
    signing_key = _signing_key(key)
    nonce = secrets.token_bytes(32)
    signature = _signature(signing_key, nonce, session_hash)
    return f"v1.{_encode(nonce)}.{_encode(signature)}"


def validate_csrf_token(token: str, key: str, session_hash: bytes | None) -> bool:
    """형식과 서명·현재 인증 결합을 확인하며 원문을 오류에 포함하지 않는다."""
    signing_key = _signing_key(key)
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


def _https_origin(value: str, *, referer: bool) -> str | None:
    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        # port 속성 접근은 숫자가 아니거나 범위를 넘는 포트를 거부한다.
        _ = parsed.port
        if not referer and (parsed.path or parsed.query or parsed.fragment):
            return None
    except ValueError:
        return None
    return f"https://{parsed.netloc}"


def _allowed_origin(request: Request, origins: tuple[str, ...]) -> bool:
    provided_origins = request.headers.getlist("origin")
    if provided_origins:
        if len(provided_origins) != 1:
            return False
        origin = _https_origin(provided_origins[0], referer=False)
        return (
            origin is not None and provided_origins[0] == origin and origin in origins
        )
    referers = request.headers.getlist("referer")
    if len(referers) != 1:
        return False
    origin = _https_origin(referers[0], referer=True)
    return origin is not None and origin in origins


async def require_csrf(
    request: Request,
    principal: Annotated[SessionPrincipal | None, Depends(get_optional_session)],
) -> None:
    """서명·쿠키/헤더·HTTPS 출처를 모두 확인한 뒤 상태 변경을 허용한다."""
    if request.method in _SAFE_METHODS:
        return
    settings = cast(Settings, request.app.state.settings)
    configured_key = settings.csrf_signing_key
    key = configured_key.get_secret_value() if configured_key is not None else ""
    _signing_key(key)
    header_values = request.headers.getlist(CSRF_HEADER_NAME)
    cookie = request.cookies.get(CSRF_COOKIE_NAME)
    session_hash = principal.token_hash if principal is not None else None
    if (
        not _allowed_origin(request, settings.auth_allowed_origins)
        or cookie is None
        or len(header_values) != 1
        or not validate_csrf_token(cookie, key, session_hash)
        or not hmac.compare_digest(cookie.encode(), header_values[0].encode())
    ):
        raise AppError(403, "FORBIDDEN", "요청을 확인할 수 없습니다.")
