"""로그인 전후의 서명된 CSRF 토큰과 상태 변경 요청의 출처를 검증한다."""

import hmac
from typing import Annotated, cast
from urllib.parse import urlsplit

from fastapi import Depends, Request

from app.core.config import Settings
from app.core.exceptions import AppError
from app.dependencies.auth import get_optional_session
from app.security.csrf import require_signing_key, validate_csrf_token
from app.services.sessions import SessionPrincipal

CSRF_COOKIE_NAME = "__Host-sku-dreamon-csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


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
    require_signing_key(key)
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
