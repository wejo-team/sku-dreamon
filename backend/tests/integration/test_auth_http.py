"""실제 세션 저장과 HTTPS 응답의 쿠키·CSRF 전환을 함께 검증한다."""

from collections.abc import AsyncIterator
from datetime import timedelta
from http.cookies import SimpleCookie
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import Settings
from app.core.db.base import Base
from app.core.db.session import Database
from app.core.http.handlers import register_error_handlers
from app.domains.auth import session_service
from app.domains.auth.csrf import CSRF_COOKIE_NAME, validate_csrf_token
from app.domains.auth.dependencies import SESSION_COOKIE_NAME
from app.domains.auth.models import Account, AuthSession
from app.domains.auth.router import router
from app.domains.auth.session_service import IssuedSession, issue_session

pytestmark = [pytest.mark.integration, pytest.mark.database]
SIGNING_KEY = "auth-http-test-key-32-bytes-long!!"
ORIGIN = "https://api.example.com"


@pytest_asyncio.fixture
async def http_database(database_url: str) -> AsyncIterator[Database]:
    schema = f"auth_http_test_{uuid4().hex}"
    engine = create_async_engine(
        database_url, execution_options={"schema_translate_map": {None: schema}}
    )
    database = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    try:
        async with engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync,
                    tables=[
                        Base.metadata.tables["accounts"],
                        Base.metadata.tables["auth_sessions"],
                    ],
                )
            )
        yield database
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


@pytest.fixture
def http_app(http_database: Database) -> FastAPI:
    app = FastAPI()
    app.state.database = http_database
    app.state.settings = Settings(
        csrf_signing_key=SecretStr(SIGNING_KEY),
        auth_allowed_origins=(ORIGIN,),
        _env_file=None,
    )
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    return app


@pytest_asyncio.fixture
async def http_client(http_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=http_app, raise_app_exceptions=False),
        base_url=ORIGIN,
    ) as client:
        yield client


async def create_login(database: Database) -> tuple[UUID, IssuedSession]:
    async with database.session() as session:
        account = Account(
            login_id_normalized="authhttp01", password_hash="never-expose-hash"
        )
        session.add(account)
        await session.flush()
        issued = await issue_session(session, account.account_id)
        await session.commit()
        return account.account_id, issued


def read_cookies(response: Response) -> SimpleCookie:
    cookies = SimpleCookie()
    for value in response.headers.get_list("set-cookie"):
        cookies.load(value)
    for cookie in cookies.values():
        assert cookie["secure"]
        assert cookie["httponly"]
        assert cookie["samesite"] == "lax"
        assert cookie["path"] == "/"
        assert not cookie["domain"]
    return cookies


async def test_anonymous_csrf_cookie_is_private_and_reused(
    http_client: AsyncClient, http_database: Database
) -> None:
    first = await http_client.get("/api/v1/auth/csrf")
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    token = first.json()["data"]["csrfToken"]
    assert first.json() == {"data": {"csrfToken": token}}
    assert validate_csrf_token(token, SIGNING_KEY, None)
    cookies = read_cookies(first)
    assert set(cookies) == {CSRF_COOKIE_NAME}
    assert cookies[CSRF_COOKIE_NAME].value == token
    second = await http_client.get("/api/v1/auth/csrf")
    assert second.json() == first.json()
    async with http_database.session() as session:
        assert await session.scalar(select(func.count()).select_from(AuthSession)) == 0


async def test_csrf_rebinds_after_login_and_session_switch(
    http_client: AsyncClient, http_database: Database
) -> None:
    anonymous = (await http_client.get("/api/v1/auth/csrf")).json()["data"]["csrfToken"]
    account_id, first_session = await create_login(http_database)
    http_client.cookies.set(SESSION_COOKIE_NAME, first_session.token)
    first = await http_client.get("/api/v1/auth/csrf")
    token = first.json()["data"]["csrfToken"]
    assert token != anonymous
    assert validate_csrf_token(token, SIGNING_KEY, first_session.session.token_hash)
    assert not validate_csrf_token(token, SIGNING_KEY, None)
    assert first_session.token not in first.text
    assert first_session.session.token_hash.hex() not in first.text
    assert set(read_cookies(first)) == {CSRF_COOKIE_NAME}
    assert (await http_client.get("/api/v1/auth/csrf")).json() == first.json()
    async with http_database.session() as session:
        second_session = await issue_session(session, account_id)
        await session.commit()
    http_client.cookies.set(SESSION_COOKIE_NAME, second_session.token)
    second = await http_client.get("/api/v1/auth/csrf")
    new_token = second.json()["data"]["csrfToken"]
    assert new_token != token
    assert validate_csrf_token(
        new_token, SIGNING_KEY, second_session.session.token_hash
    )
    assert not validate_csrf_token(
        new_token, SIGNING_KEY, first_session.session.token_hash
    )


@pytest.mark.parametrize(
    "invalid", ["idle", "absolute", "revoked", "unknown", "malformed"]
)
async def test_invalid_session_gets_anonymous_csrf_and_cookie_deletion(
    http_client: AsyncClient,
    http_database: Database,
    monkeypatch: pytest.MonkeyPatch,
    invalid: str,
) -> None:
    _, issued = await create_login(http_database)
    http_client.cookies.set(SESSION_COOKIE_NAME, issued.token)
    before = (await http_client.get("/api/v1/auth/csrf")).json()["data"]["csrfToken"]
    if invalid in {"idle", "absolute"}:
        delta = timedelta(hours=24) if invalid == "idle" else timedelta(days=7)
        monkeypatch.setattr(
            session_service,
            "_utcnow",
            lambda: issued.session.created_at + delta + timedelta(seconds=1),
        )
    elif invalid == "revoked":
        async with http_database.session() as session:
            row = await session.get(AuthSession, issued.session.auth_session_id)
            assert row is not None
            row.revoked_at = row.created_at
            await session.commit()
    else:
        http_client.cookies.set(
            SESSION_COOKIE_NAME, "z" * 43 if invalid == "unknown" else "bad"
        )
    response = await http_client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    token = response.json()["data"]["csrfToken"]
    assert token != before
    assert validate_csrf_token(token, SIGNING_KEY, None)
    cookies = read_cookies(response)
    assert cookies[SESSION_COOKIE_NAME]["max-age"] == "0"
    assert cookies[SESSION_COOKIE_NAME].value == ""
    assert cookies[CSRF_COOKIE_NAME].value == token
    async with http_database.session() as session:
        assert await session.scalar(select(func.count()).select_from(AuthSession)) == 1


async def test_missing_signing_key_does_not_issue_cookies(
    http_client: AsyncClient, http_app: FastAPI
) -> None:
    http_app.state.settings = Settings(_env_file=None)
    response = await http_client.get("/api/v1/auth/csrf")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TEMPORARY_UNAVAILABLE"
    assert "set-cookie" not in response.headers


async def test_invalid_csrf_cookie_is_replaced(
    http_client: AsyncClient, http_app: FastAPI
) -> None:
    http_client.cookies.set(CSRF_COOKIE_NAME, "tampered")
    response = await http_client.get("/api/v1/auth/csrf")
    token = response.json()["data"]["csrfToken"]
    assert validate_csrf_token(token, SIGNING_KEY, None)
    assert read_cookies(response)[CSRF_COOKIE_NAME].value == token
    operation = http_app.openapi()["paths"]["/api/v1/auth/csrf"]["get"]
    assert {} in operation["security"]
    assert set(operation["responses"]) == {"200", "500", "503"}
