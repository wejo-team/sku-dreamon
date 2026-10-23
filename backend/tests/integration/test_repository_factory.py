"""레포지토리 간 트랜잭션 공유와 세션 종료 시 DB 일관성을 검증한다."""

from collections.abc import AsyncIterator
from contextlib import nullcontext
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.db.factories import RepositoryFactory
from app.core.db.session import Database

pytestmark = [pytest.mark.integration, pytest.mark.database]


class ProbeRepository:
    def __init__(self, db_session: AsyncSession, schema: str) -> None:
        self.db_session = db_session
        self.schema = schema

    async def add(self, value: int) -> None:
        await self.db_session.execute(
            text(f"INSERT INTO {self.schema}.probe VALUES (:value)"), {"value": value}
        )

    async def values(self) -> list[int]:
        result = await self.db_session.execute(
            text(f"SELECT value FROM {self.schema}.probe ORDER BY value")
        )
        return [int(value) for value in result.scalars()]


@pytest_asyncio.fixture
async def probe_database(database_url: str) -> AsyncIterator[tuple[Database, str]]:
    # 반환되지 않은 연결이 있으면 다음 조회가 실패하도록 풀을 하나로 제한한다.
    engine = create_async_engine(
        database_url, pool_size=1, max_overflow=0, pool_timeout=1
    )
    database = Database(
        engine=engine,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )
    schema = f"wejo_factory_test_{uuid4().hex}"
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
            await connection.execute(
                text(f"CREATE TABLE {schema}.probe (value integer NOT NULL)")
            )
        try:
            yield database, schema
        finally:
            async with engine.begin() as connection:
                await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    finally:
        await engine.dispose()


@pytest.mark.parametrize("commit", [False, True])
async def test_borrowed_repositories_share_the_callers_transaction(
    probe_database: tuple[Database, str], commit: bool
) -> None:
    database, schema = probe_database
    factory = RepositoryFactory(
        repository_class=lambda session: ProbeRepository(session, schema)
    )

    async with database.session() as session:
        first = factory.create_repository(session)
        await first.add(1)
        second = factory.create_repository(session)
        assert await second.values() == [1]
        await second.add(2)
        assert await first.values() == [1, 2]
        if commit:
            await session.commit()

    async with database.session() as session:
        reader = factory.create_repository(session)
        assert await reader.values() == ([1, 2] if commit else [])


@pytest.mark.parametrize(
    ("commit", "fail", "expected_values"),
    [(False, False, []), (True, False, [3]), (False, True, [])],
)
async def test_owned_scope_releases_connection_and_preserves_only_explicit_commits(
    probe_database: tuple[Database, str],
    commit: bool,
    fail: bool,
    expected_values: list[int],
) -> None:
    database, schema = probe_database
    factory = RepositoryFactory(
        repository_class=lambda session: ProbeRepository(session, schema),
        database=database,
    )

    expected_error = (
        pytest.raises(RuntimeError, match="operation failed") if fail else nullcontext()
    )
    with expected_error:
        async with factory.open_repository() as repository:
            await repository.add(3)
            if commit:
                await repository.db_session.commit()
            if fail:
                raise RuntimeError("operation failed")

    async with factory.open_repository() as reader:
        assert await reader.values() == expected_values
