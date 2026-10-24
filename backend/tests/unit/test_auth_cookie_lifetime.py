"""응답 지연이 인증 쿠키의 서버 절대 만료를 연장하지 않는지 확인한다."""

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

from fastapi import Response

from app.dependencies.auth import SESSION_COOKIE_NAME
from app.models.auth import AuthSession
from app.routers.auth_cookies import set_session_cookie
from app.services.sessions import IssuedSession


def test_delayed_issue_uses_remaining_absolute_lifetime() -> None:
    before = datetime.now(UTC)
    expires = before + timedelta(days=7) - timedelta(seconds=30)
    issued = IssuedSession(token="test-token", session=AuthSession(expires_at=expires))
    response = Response()
    set_session_cookie(response, issued)
    cookie = SimpleCookie(response.headers["set-cookie"])[SESSION_COOKIE_NAME]
    max_age = int(cookie["max-age"])
    assert 0 < max_age <= 7 * 24 * 60 * 60 - 30
    assert before + timedelta(seconds=max_age) <= expires
