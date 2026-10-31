"""가입·로그인의 쿠키 전환, 실패 원자성, 공유 시도 제한을 검증한다."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.db.session import Database
from app.models.auth import Account
from tests.integration.test_auth_http import ORIGIN

pytest_plugins = ["tests.integration.test_auth_http"]

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def headers(client: AsyncClient) -> dict[str, str]:
    response = await client.get("/api/v1/auth/csrf")
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["data"]["csrfToken"]}


async def test_signup_login_and_availability(
    http_client: AsyncClient, http_database: Database, http_app: FastAPI
) -> None:
    from app.security.passwords import PasswordBlocklist

    http_app.state.password_blocklist = PasswordBlocklist(
        version="test", _passwords=frozenset({"blocked-password-123"})
    )
    credentials = {"loginId": " NEWUSER ", "password": "abcdefg!"}
    missing_symbol = await http_client.post(
        "/api/v1/accounts",
        json={**credentials, "password": "abcdefgh"},
        headers=await headers(http_client),
    )
    assert missing_symbol.status_code == 422
    assert missing_symbol.json()["detail"][0]["loc"] == ["body", "password"]
    assert "abcdefgh" not in missing_symbol.text
    response = await http_client.post(
        "/api/v1/accounts", json=credentials, headers=await headers(http_client)
    )
    assert response.status_code == 201, response.text
    account = response.json()["data"]["account"]
    assert account["loginId"] == "newuser" and not account["hasProfile"]
    assert (await http_client.get("/api/v1/me")).json()["data"]["id"] == account["id"]
    assert "password" not in response.text and "token" not in response.text.lower()
    available = await http_client.get(
        "/api/v1/auth/login-id-availability", params={"loginId": "NewUser"}
    )
    assert available.json()["data"] == {
        "normalizedLoginId": "newuser",
        "available": False,
    }
    duplicate = await http_client.post(
        "/api/v1/accounts", json=credentials, headers=await headers(http_client)
    )
    assert duplicate.status_code == 409
    await http_client.post("/api/v1/auth/logout", headers=await headers(http_client))
    bad = await http_client.post(
        "/api/v1/auth/login",
        json={**credentials, "password": "Incorrect long password"},
        headers=await headers(http_client),
    )
    assert bad.status_code == 401
    good = await http_client.post(
        "/api/v1/auth/login", json=credentials, headers=await headers(http_client)
    )
    assert good.status_code == 200
    assert good.json()["data"]["account"]["id"] == account["id"]
    async with http_database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Account)) == 1


async def test_existing_password_without_symbols_still_logs_in(
    http_client: AsyncClient, http_database: Database
) -> None:
    from app.security.passwords import hash_password

    password = "Existing password without symbols"
    async with http_database.session() as session:
        account = Account(
            login_id_normalized="legacyuser",
            password_hash=await hash_password(password),
        )
        session.add(account)
        await session.commit()
        account_id = str(account.account_id)

    response = await http_client.post(
        "/api/v1/auth/login",
        json={"loginId": "legacyuser", "password": password},
        headers=await headers(http_client),
    )
    assert response.status_code == 200
    assert response.json()["data"]["account"]["id"] == account_id


async def test_unconfigured_signup_and_csrf_fail_without_account(
    http_client: AsyncClient, http_database: Database
) -> None:
    credentials = {"loginId": "newuser", "password": "abcdefg!"}
    assert (
        await http_client.post("/api/v1/accounts", json=credentials)
    ).status_code == 403
    response = await http_client.post(
        "/api/v1/accounts", json=credentials, headers=await headers(http_client)
    )
    assert response.status_code == 503
    async with http_database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Account)) == 0


async def test_unknown_account_attempt_limit(http_client: AsyncClient) -> None:
    for _ in range(10):
        response = await http_client.post(
            "/api/v1/auth/login",
            json={"loginId": "unknown", "password": "Long unknown password"},
            headers=await headers(http_client),
        )
        assert response.status_code == 401, response.text
    response = await http_client.post(
        "/api/v1/auth/login",
        json={"loginId": "unknown", "password": "Long unknown password"},
        headers=await headers(http_client),
    )
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


async def test_signup_session_failure_rolls_back_account(
    http_client: AsyncClient,
    http_database: Database,
    http_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.security.passwords import PasswordBlocklist
    from app.services import auth as service
    from app.services.sessions import IssuedSession

    http_app.state.password_blocklist = PasswordBlocklist(
        version="test", _passwords=frozenset({"blocked-password-123"})
    )

    async def fail(session: AsyncSession, account_id: UUID) -> IssuedSession:
        raise RuntimeError("session storage failure")

    monkeypatch.setattr(service, "issue_session", fail)
    response = await http_client.post(
        "/api/v1/accounts",
        json={"loginId": "rollback", "password": "abcdefg!"},
        headers=await headers(http_client),
    )
    assert response.status_code == 500
    assert "set-cookie" not in response.headers
    async with http_database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Account)) == 0


async def test_concurrent_signup_has_one_account_and_session(
    http_database: Database,
) -> None:
    import asyncio

    from app.core.exceptions import AppError
    from app.models.auth import AuthSession
    from app.schemas.auth import SignupCredentials
    from app.security.passwords import PasswordBlocklist
    from app.services.auth import signup

    async def create() -> int:
        async with http_database.session() as session:
            try:
                await signup(
                    session,
                    SignupCredentials(loginId="sameuser", password="abcdefg!"),
                    PasswordBlocklist(
                        version="test", _passwords=frozenset({"blocked-password-123"})
                    ),
                )
                return 201
            except AppError as error:
                return error.status_code

    assert sorted(await asyncio.gather(create(), create())) == [201, 409]
    async with http_database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Account)) == 1
        assert await session.scalar(select(func.count()).select_from(AuthSession)) == 1


async def test_attempts_are_shared_under_concurrency_and_reset_at_boundary(
    http_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    from datetime import UTC, datetime, timedelta

    from app.core.exceptions import AppError
    from app.services import auth_attempts

    start = datetime(2026, 10, 24, tzinfo=UTC)
    monkeypatch.setattr(auth_attempts, "_utcnow", lambda: start)

    async def attempt() -> int:
        try:
            await auth_attempts.consume(http_database, [("concurrent", 3)])
            return 200
        except AppError as error:
            return error.status_code

    results = await asyncio.gather(*(attempt() for _ in range(8)))
    assert results.count(200) == 3 and results.count(429) == 5
    monkeypatch.setattr(auth_attempts, "_utcnow", lambda: start + timedelta(minutes=15))
    assert await attempt() == 200


async def test_blocked_password_and_invalid_alias_never_create_account(
    http_client: AsyncClient, http_database: Database, http_app: FastAPI
) -> None:
    from app.security.passwords import PasswordBlocklist

    http_app.state.password_blocklist = PasswordBlocklist(
        version="test", _passwords=frozenset({"blocked-password-123"})
    )
    response = await http_client.post(
        "/api/v1/accounts",
        json={"loginId": "blocked", "password": "blocked-password-123"},
        headers=await headers(http_client),
    )
    assert (
        response.status_code == 400
        and response.json()["error"]["code"] == "PASSWORD_BLOCKED"
    )
    response = await http_client.post(
        "/api/v1/accounts",
        json={"login_id": "blocked", "password": "blocked-password-123"},
        headers=await headers(http_client),
    )
    assert response.status_code == 422
    assert "blocked-password-123" not in response.text
    async with http_database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Account)) == 0
