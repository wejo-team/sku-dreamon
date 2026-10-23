"""서버 세션·CSRF와 쿠키를 인증 HTTP 계약에 연결한다."""

from typing import cast

from fastapi import APIRouter, Request, Response

from app.core.config import Settings
from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.schemas import Success
from app.domains.auth import http_service
from app.domains.auth.cookies import delete_session_cookie, set_csrf_cookie
from app.domains.auth.csrf import CSRF_COOKIE_NAME, get_or_create_csrf_token
from app.domains.auth.dependencies import (
    SESSION_COOKIE_NAME,
    CurrentAccount,
    OptionalSession,
)
from app.domains.auth.schemas import AccountResponse, CsrfToken

router = APIRouter(tags=["auth"])


@router.get(
    "/auth/csrf",
    response_model=Success[CsrfToken],
    responses=error_responses(500, 503),
    openapi_extra={"security": [{}]},
    summary="현재 인증 상태의 CSRF 토큰",
)
async def get_csrf(
    request: Request, response: Response, principal: OptionalSession
) -> Success[CsrfToken]:
    settings = cast(Settings, request.app.state.settings)
    configured_key = settings.csrf_signing_key
    key = configured_key.get_secret_value() if configured_key is not None else ""
    token = get_or_create_csrf_token(
        request.cookies.get(CSRF_COOKIE_NAME),
        key,
        principal.token_hash if principal is not None else None,
    )
    response.headers["Cache-Control"] = "no-store"
    if principal is None and SESSION_COOKIE_NAME in request.cookies:
        delete_session_cookie(response)
    set_csrf_cookie(response, token)
    return Success(data=CsrfToken(csrf_token=token))


@router.get(
    "/me",
    response_model=Success[AccountResponse],
    responses=error_responses(401, 500, 503),
    summary="본인 계정",
)
async def get_me(
    response: Response, account_id: CurrentAccount, session: DatabaseSession
) -> Success[AccountResponse]:
    account = await http_service.get_account(session, account_id)
    response.headers["Cache-Control"] = "no-store"
    return Success(data=account)
