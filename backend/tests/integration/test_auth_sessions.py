"""독립 PostgreSQL 트랜잭션에서 로그인 세션의 만료·회수·경쟁을 검증한다."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.db.base import Base
from app.core.db.session import Database
from app.core.http.handlers import register_error_handlers
from app.dependencies.auth import (
    SESSION_COOKIE_NAME,
    CurrentAccount,
    CurrentSession,
    OptionalAccount,
)
from app.models.auth import Account, AuthSession
from app.services import sessions as session_service
from app.services.sessions import (
    IssuedSession,
    authenticate_session,
    issue_session,
    revoke_session,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest_asyncio.fixture
async def auth_database(database_url: str) -> AsyncIterator[Database]:
    schema = f"sessions_test_{uuid4().hex}"
    engine = create_async_engine(
        database_url,
        execution_options={"schema_translate_map": {None: schema}},
        connect_args={"server_settings": {"application_name": schema}},
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


async def create_login(database: Database) -> tuple[UUID, IssuedSession]:
    async with database.session() as session:
        account = Account(login_id_normalized="dreamon01", password_hash="test-hash")
        session.add(account)
        await session.flush()
        issued = await issue_session(session, account.account_id)
        await session.commit()
        return account.account_id, issued


async def test_issue_joins_the_callers_transaction_and_persists_only_hash(
    auth_database: Database,
) -> None:
    account_id, issued = await create_login(auth_database)
    assert issued.token not in repr(issued)
    assert issued.session.expires_at - issued.session.created_at == timedelta(days=7)
    async with auth_database.session() as session:
        assert await session.get(Account, account_id) is not None
        row = await session.get(AuthSession, issued.session.auth_session_id)
        assert row is not None
        assert len(row.token_hash) == 32
        assert issued.token.encode() != row.token_hash
        discarded = await issue_session(session, account_id)
    assert await authenticate_session(auth_database, discarded.token) is None
    principal = await authenticate_session(auth_database, issued.token)
    assert principal is not None
    assert principal.account_id == account_id
    assert principal.token_hash == row.token_hash
    assert row.token_hash.hex() not in repr(principal)


@pytest.mark.parametrize("boundary", ["idle", "absolute"])
@pytest.mark.parametrize("offset", [-1, 0, 1])
async def test_expiry_boundaries_are_checked_before_activity_update(
    auth_database: Database,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    offset: int,
) -> None:
    _, issued = await create_login(auth_database)
    start = issued.session.created_at
    expiry = (
        start + timedelta(hours=24) if boundary == "idle" else start + timedelta(days=7)
    )
    if boundary == "absolute":
        async with auth_database.session() as session:
            row = await session.get(AuthSession, issued.session.auth_session_id)
            assert row is not None
            row.last_seen_at = expiry - timedelta(hours=1)
            await session.commit()
    check_time = expiry + timedelta(microseconds=offset)
    monkeypatch.setattr(session_service, "_utcnow", lambda: check_time)
    principal = await authenticate_session(auth_database, issued.token)
    assert (principal is not None) is (offset < 0)
    if principal is None:
        async with auth_database.session() as session:
            row = await session.get(AuthSession, issued.session.auth_session_id)
            assert row is not None
            assert row.last_seen_at != check_time


async def test_sessions_are_independent_and_revocation_does_not_revoke_others(
    auth_database: Database,
) -> None:
    account_id, first = await create_login(auth_database)
    async with auth_database.session() as session:
        second = await issue_session(session, account_id)
        await session.commit()
    principal = await authenticate_session(auth_database, first.token)
    assert principal is not None
    async with auth_database.session() as session:
        assert await revoke_session(session, principal)
        await session.commit()
    assert await authenticate_session(auth_database, first.token) is None
    assert await authenticate_session(auth_database, second.token) is not None
    async with auth_database.session() as session:
        second_row = await session.get(AuthSession, second.session.auth_session_id)
        assert second_row is not None
        assert second_row.revoked_at is None
        assert second_row.expires_at == second.session.expires_at


async def test_business_rollback_does_not_rollback_authentication_activity(
    auth_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    account_id, issued = await create_login(auth_database)
    next_activity = issued.session.created_at + timedelta(hours=1)
    monkeypatch.setattr(session_service, "_utcnow", lambda: next_activity)
    assert await authenticate_session(auth_database, issued.token) is not None
    async with auth_database.session() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        account.login_id_normalized = "rolledback"
        await session.flush()
        await session.rollback()
    async with auth_database.session() as session:
        row = await session.get(AuthSession, issued.session.auth_session_id)
        assert row is not None
        assert row.last_seen_at == next_activity
        account = await session.get(Account, account_id)
        assert account is not None
        assert account.login_id_normalized == "dreamon01"


@pytest.mark.parametrize("change", ["revoke", "expire"])
async def test_waiting_authentication_observes_revocation_and_time_after_lock(
    auth_database: Database, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    _, issued = await create_login(auth_database)
    current_time = [issued.session.created_at + timedelta(hours=1)]
    monkeypatch.setattr(session_service, "_utcnow", lambda: current_time[0])
    async with auth_database.session() as holding_session:
        row = await holding_session.scalar(
            select(AuthSession)
            .where(AuthSession.auth_session_id == issued.session.auth_session_id)
            .with_for_update()
        )
        assert row is not None
        pending = asyncio.create_task(authenticate_session(auth_database, issued.token))
        try:
            # 연결이 실제 잠금을 기다리는 것을 확인해 테스트 스케줄링에 의존하지 않는다.
            async with asyncio.timeout(5):
                async with auth_database.engine.connect() as observer:
                    app_name = await observer.scalar(text("SHOW application_name"))
                    # DB의 잠금 대기는 Python Event로 통지되지 않으므로 조회한다.
                    while True:
                        waiting = await observer.scalar(
                            text(
                                "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                "WHERE application_name = :name "
                                "AND wait_event_type = 'Lock')"
                            ),
                            {"name": app_name},
                        )
                        await observer.commit()
                        if waiting:
                            break
                        await asyncio.sleep(0.01)
            if change == "revoke":
                row.revoked_at = current_time[0]
            else:
                current_time[0] = issued.session.created_at + timedelta(hours=24)
            await holding_session.commit()
            assert await pending is None
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


async def test_missing_unknown_and_malformed_tokens_do_not_authenticate(
    auth_database: Database,
) -> None:
    for token in (None, "", "not-a-token", "x" * 43):
        assert await authenticate_session(auth_database, token) is None


async def test_http_dependencies_share_identity_and_keep_optional_access_public(
    auth_database: Database,
) -> None:
    account_id, issued = await create_login(auth_database)
    app = FastAPI()
    app.state.database = auth_database
    register_error_handlers(app)

    @app.get("/private")
    async def private(
        account: CurrentAccount, session: CurrentSession
    ) -> dict[str, UUID]:
        return {"account": account, "session": session.auth_session_id}

    @app.get("/public")
    async def public(account: OptionalAccount) -> dict[str, UUID | None]:
        return {"account": account}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        assert (await client.get("/public")).json() == {"account": None}
        assert (await client.get("/private")).status_code == 401
        client.cookies.set(SESSION_COOKIE_NAME, issued.token)
        response = await client.get("/private")
        assert response.status_code == 200
        assert response.json() == {
            "account": str(account_id),
            "session": str(issued.session.auth_session_id),
        }
        assert issued.token not in response.text
        assert (await client.get("/public")).json() == {"account": str(account_id)}
        client.cookies.set(SESSION_COOKIE_NAME, "invalid-token")
        assert (await client.get("/public")).json() == {"account": None}
        assert (await client.get("/private")).json()["error"][
            "code"
        ] == "UNAUTHENTICATED"
    assert app.openapi()["components"]["securitySchemes"]["SessionCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": SESSION_COOKIE_NAME,
    }
