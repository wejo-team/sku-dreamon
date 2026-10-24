"""인증 쿠키의 HTTPS·호스트 전용 속성을 발급과 삭제에 동일하게 적용한다."""

from fastapi import Response

from app.dependencies.auth import SESSION_COOKIE_NAME
from app.dependencies.csrf import CSRF_COOKIE_NAME
from app.services.sessions import IssuedSession


def set_session_cookie(response: Response, issued: IssuedSession) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        issued.token,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        expires=issued.session.expires_at,
    )


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax"
    )


def delete_auth_cookies(response: Response) -> None:
    delete_session_cookie(response)
    response.delete_cookie(
        CSRF_COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax"
    )
