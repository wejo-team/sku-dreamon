"""실제 HTTP 요청의 출처·쿠키·헤더와 현재 세션 결합을 검증한다."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.http.handlers import register_error_handlers
from app.dependencies.auth import get_optional_session
from app.dependencies.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, require_csrf
from app.security.csrf import issue_csrf_token
from app.services.sessions import SessionPrincipal

pytestmark = pytest.mark.integration
ORIGIN = "https://app.example.com"
SIGNING_KEY = "test-only-signing-key-with-at-least-32-bytes"


def make_app(principal: SessionPrincipal | None = None) -> FastAPI:
    app = FastAPI()
    app.state.settings = Settings(
        csrf_signing_key=SecretStr(SIGNING_KEY),
        auth_allowed_origins=(ORIGIN,),
        _env_file=None,
    )
    app.state.writes = 0
    register_error_handlers(app)

    async def optional_session() -> SessionPrincipal | None:
        return principal

    app.dependency_overrides[get_optional_session] = optional_session

    @app.post("/write", dependencies=[Depends(require_csrf)])
    async def write() -> dict[str, bool]:
        app.state.writes += 1
        return {"ok": True}

    @app.get("/read", dependencies=[Depends(require_csrf)])
    async def read() -> dict[str, bool]:
        return {"ok": True}

    return app


def token_headers(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token, "Cookie": f"{CSRF_COOKIE_NAME}={token}"}


@pytest.mark.parametrize(
    ("origin_headers", "expected_status"),
    [
        ({"Origin": ORIGIN}, 200),
        ({"Referer": f"{ORIGIN}/form?tab=signup"}, 200),
        ({}, 403),
        ({"Origin": "null"}, 403),
        ({"Origin": ""}, 403),
        ({"Origin": "http://app.example.com"}, 403),
        ({"Origin": f"{ORIGIN}.attacker.test"}, 403),
        ({"Origin": f"{ORIGIN}/"}, 403),
        ({"Origin": "https://attacker.test", "Referer": ORIGIN}, 403),
        ({"Referer": "https://user@app.example.com/form"}, 403),
        ({"Referer": "https://app.example.com:bad/form"}, 403),
        ({"Referer": "https://attacker.test/form"}, 403),
    ],
)
async def test_origin_validation_precedes_business_writes(
    origin_headers: dict[str, str], expected_status: int
) -> None:
    app = make_app()
    token = issue_csrf_token(SIGNING_KEY, None)
    headers = token_headers(token) | origin_headers

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        response = await client.post("/write", headers=headers)

    assert response.status_code == expected_status
    assert app.state.writes == (1 if expected_status == 200 else 0)
    if expected_status == 403:
        assert response.json()["error"]["code"] == "FORBIDDEN"
        assert token not in response.text


@pytest.mark.parametrize("kind", ["no-cookie", "no-header", "mismatch", "forged"])
async def test_invalid_cookie_header_pair_cannot_change_state(kind: str) -> None:
    app = make_app()
    token = issue_csrf_token(SIGNING_KEY, None)
    headers = token_headers(token) | {"Origin": ORIGIN}
    if kind == "no-cookie":
        del headers["Cookie"]
    elif kind == "no-header":
        del headers[CSRF_HEADER_NAME]
    elif kind == "mismatch":
        headers[CSRF_HEADER_NAME] = issue_csrf_token(SIGNING_KEY, None)
    else:
        headers = token_headers("forged") | {"Origin": ORIGIN}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        response = await client.post("/write", headers=headers)

    assert response.status_code == 403
    assert app.state.writes == 0


async def test_current_valid_session_is_required_for_an_authenticated_token() -> None:
    session_hash = b"a" * 32
    principal = SessionPrincipal(
        auth_session_id=uuid4(),
        account_id=uuid4(),
        token_hash=session_hash,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    anonymous = issue_csrf_token(SIGNING_KEY, None)
    authenticated = issue_csrf_token(SIGNING_KEY, session_hash)
    app = make_app(principal)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        rejected = await client.post(
            "/write", headers=token_headers(anonymous) | {"Origin": ORIGIN}
        )
        accepted = await client.post(
            "/write", headers=token_headers(authenticated) | {"Origin": ORIGIN}
        )

    assert rejected.status_code == 403
    assert accepted.status_code == 200
    assert app.state.writes == 1

    expired_app = make_app()
    async with AsyncClient(
        transport=ASGITransport(app=expired_app), base_url="https://api.example.com"
    ) as client:
        expired = await client.post(
            "/write", headers=token_headers(authenticated) | {"Origin": ORIGIN}
        )
        relogin = await client.post(
            "/write", headers=token_headers(anonymous) | {"Origin": ORIGIN}
        )
    assert expired.status_code == 403
    assert relogin.status_code == 200


async def test_missing_key_fails_closed_and_safe_methods_do_not_require_csrf() -> None:
    app = make_app()
    app.state.settings = Settings(_env_file=None, auth_allowed_origins=(ORIGIN,))
    token = issue_csrf_token(SIGNING_KEY, None)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        unavailable = await client.post(
            "/write", headers=token_headers(token) | {"Origin": ORIGIN}
        )
        readable = await client.get("/read")

    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "TEMPORARY_UNAVAILABLE"
    assert readable.status_code == 200
    assert app.state.writes == 0
