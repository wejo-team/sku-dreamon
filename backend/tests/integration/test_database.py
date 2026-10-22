import asyncio
from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import PostgresDsn
from sqlalchemy import Engine, event, text

from app.core.config import Settings
from app.db.session import Database, DatabaseSession
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest_asyncio.fixture
async def database_app(database_url: str) -> AsyncIterator[FastAPI]:
    settings = Settings(database_url=PostgresDsn(database_url), _env_file=None)
    app = create_app(settings)
    async with LifespanManager(app):
        yield app


async def test_concurrent_requests_use_independent_sessions(
    database_app: FastAPI,
) -> None:
    barrier = asyncio.Barrier(2)

    @database_app.get("/test/session")
    async def inspect_session(session: DatabaseSession) -> dict[str, int]:
        result = await session.execute(text("SELECT pg_backend_pid()"))
        connection_id = result.scalar_one()
        async with asyncio.timeout(10):
            await barrier.wait()
        return {"session_id": id(session), "connection_id": connection_id}

    async with AsyncClient(
        transport=ASGITransport(app=database_app), base_url="http://test"
    ) as client:
        first, second = await asyncio.gather(
            client.get("/test/session"), client.get("/test/session")
        )

    assert first.status_code == second.status_code == 200
    assert first.json()["session_id"] != second.json()["session_id"]
    assert first.json()["connection_id"] != second.json()["connection_id"]


@pytest.mark.parametrize(
    ("commit", "fail", "expected_status", "expected_rows"),
    [(False, False, 200, 0), (True, False, 200, 1), (False, True, 409, 0)],
)
async def test_request_cleanup_preserves_only_explicit_commits(
    database_app: FastAPI,
    commit: bool,
    fail: bool,
    expected_status: int,
    expected_rows: int,
) -> None:
    database = cast(Database, database_app.state.database)
    # A unique, disposable schema keeps every case isolated, including real commits.
    schema = f"wejo_test_{uuid4().hex}"
    async with database.engine.begin() as connection:
        await connection.execute(text(f"CREATE SCHEMA {schema}"))
        await connection.execute(text(f"CREATE TABLE {schema}.probe (value integer)"))

    @database_app.post("/test/write")
    async def write(session: DatabaseSession) -> dict[str, bool]:
        await session.execute(text(f"INSERT INTO {schema}.probe VALUES (1)"))
        if fail:
            raise HTTPException(status_code=409, detail="Simulated failure")
        if commit:
            await session.commit()
        return {"ok": True}

    try:
        async with AsyncClient(
            transport=ASGITransport(app=database_app), base_url="http://test"
        ) as client:
            response = await client.post("/test/write")
        assert response.status_code == expected_status
        async with database.engine.connect() as connection:
            count = await connection.scalar(
                text(f"SELECT count(*) FROM {schema}.probe")
            )
        assert count == expected_rows
    finally:
        async with database.engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))


async def test_shutdown_disposes_the_database_pool(database_url: str) -> None:
    app = create_app(Settings(database_url=PostgresDsn(database_url), _env_file=None))
    disposed: list[Engine] = []
    async with LifespanManager(app):
        database = cast(Database, app.state.database)
        event.listen(database.engine.sync_engine, "engine_disposed", disposed.append)
        async with database.engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1

    assert disposed == [database.engine.sync_engine]
