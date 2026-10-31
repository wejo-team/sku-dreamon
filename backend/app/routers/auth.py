"""서버 세션·CSRF와 쿠키를 인증 HTTP 계약에 연결한다."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.config import Settings
from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.schemas import Success
from app.dependencies.auth import (
    SESSION_COOKIE_NAME,
    CurrentAccount,
    CurrentSession,
    OptionalSession,
    get_current_session,
)
from app.dependencies.auth_attempts import limit_auth
from app.dependencies.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, require_csrf
from app.routers.auth_cookies import (
    delete_auth_cookies,
    delete_session_cookie,
    set_csrf_cookie,
    set_session_cookie,
)
from app.schemas.auth import (
    AccountResponse,
    AuthResult,
    Credentials,
    CsrfToken,
    LoginId,
    LoginIdAvailability,
    SignupCredentials,
)
from app.security.csrf import get_or_create_csrf_token
from app.security.passwords import PasswordBlocklist
from app.services import auth as http_service

router = APIRouter(tags=["auth"])


@router.get(
    "/auth/login-id-availability",
    response_model=Success[LoginIdAvailability],
    responses=error_responses(422, 429, 500, 503),
    summary="로그인 아이디 중복 확인",
)
async def login_id_availability(
    request: Request,
    response: Response,
    session: DatabaseSession,
    login_id: Annotated[LoginId, Query(alias="loginId")],
) -> Success[LoginIdAvailability]:
    await limit_auth(request, "availability")
    response.headers["Cache-Control"] = "no-store"
    return Success(data=await http_service.login_id_availability(session, login_id))


def _finish_login(
    response: Response, result: http_service.AuthenticatedAccount
) -> Success[AuthResult]:
    response.headers["Cache-Control"] = "no-store"
    set_session_cookie(response, result.issued)
    # 이전 인증 상태의 CSRF는 폐기하고 /auth/csrf로 새 상태에 결합한다.
    response.delete_cookie(
        CSRF_COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax"
    )
    return Success(data=AuthResult(account=result.account))


@router.post(
    "/accounts",
    status_code=201,
    response_model=Success[AuthResult],
    dependencies=[Depends(require_csrf)],
    responses=error_responses(400, 403, 409, 422, 429, 500, 503),
    summary="회원가입과 자동 로그인",
)
async def signup(
    request: Request,
    response: Response,
    session: DatabaseSession,
    credentials: SignupCredentials,
) -> Success[AuthResult]:
    await limit_auth(request, "signup")
    blocklist = cast(
        PasswordBlocklist | None, getattr(request.app.state, "password_blocklist", None)
    )
    return _finish_login(
        response, await http_service.signup(session, credentials, blocklist)
    )


@router.post(
    "/auth/login",
    response_model=Success[AuthResult],
    dependencies=[Depends(require_csrf)],
    responses=error_responses(401, 403, 422, 429, 500, 503),
    summary="아이디·비밀번호 로그인",
)
async def login(
    request: Request,
    response: Response,
    session: DatabaseSession,
    credentials: Credentials,
) -> Success[AuthResult]:
    await limit_auth(request, "login", credentials.login_id)
    return _finish_login(response, await http_service.login(session, credentials))


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


@router.post(
    "/auth/logout",
    status_code=204,
    response_class=Response,
    responses=error_responses(401, 403, 500, 503),
    dependencies=[Depends(get_current_session), Depends(require_csrf)],
    openapi_extra={
        "parameters": [
            {
                "name": CSRF_HEADER_NAME,
                "in": "header",
                "required": True,
                "schema": {"type": "string"},
                "description": "현재 CSRF 쿠키와 같은 토큰. 누락·불일치 시 403.",
            }
        ]
    },
    summary="현재 세션 로그아웃",
)
async def logout(principal: CurrentSession, session: DatabaseSession) -> Response:
    await http_service.logout(session, principal)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    delete_auth_cookies(response)
    return response
