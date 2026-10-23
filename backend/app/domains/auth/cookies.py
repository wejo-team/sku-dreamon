"""인증 쿠키의 HTTPS·호스트 전용 속성을 발급과 삭제에 동일하게 적용한다."""

from fastapi import Response

from app.domains.auth.csrf import CSRF_COOKIE_NAME
from app.domains.auth.dependencies import SESSION_COOKIE_NAME


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
