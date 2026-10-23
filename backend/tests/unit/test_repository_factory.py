"""레포지토리 생성 계약과 세션 소유권을 검증한다."""

from collections.abc import AsyncIterator
from typing import assert_type

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.db.factories import RepositoryFactory
from app.core.db.session import Database


class TrackedSession(AsyncSession):
    was_closed = False

    async def close(self) -> None:
        await super().close()
        self.was_closed = True


class ExampleRepository:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    engine = create_async_engine(
        "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"
    )
    try:
        yield Database(
            engine=engine,
            session_factory=async_sessionmaker[AsyncSession](
                engine, class_=TrackedSession, expire_on_commit=False
            ),
        )
    finally:
        await engine.dispose()


async def test_borrowed_session_and_repository_type_are_preserved() -> None:
    factory = RepositoryFactory(repository_class=ExampleRepository)
    async with TrackedSession() as session:
        repository = factory.create_repository(session)
        assert_type(repository, ExampleRepository)
        assert repository.db_session is session
        assert not session.was_closed
    assert session.was_closed


async def test_owned_repository_requires_a_database() -> None:
    factory = RepositoryFactory(repository_class=ExampleRepository)
    with pytest.raises(ValueError):
        async with factory.open_repository():
            pytest.fail("DB 없이 레포지토리 사용 범위에 진입하면 안 됩니다.")


async def test_constructor_failure_closes_owned_session(database: Database) -> None:
    created_sessions: list[AsyncSession] = []

    def fail_to_build(session: AsyncSession) -> ExampleRepository:
        created_sessions.append(session)
        raise RuntimeError("repository construction failed")

    factory = RepositoryFactory(repository_class=fail_to_build, database=database)
    with pytest.raises(RuntimeError, match="repository construction failed"):
        async with factory.open_repository():
            pytest.fail("실패한 생성자가 레포지토리를 제공하면 안 됩니다.")

    assert len(created_sessions) == 1
    session = created_sessions[0]
    assert isinstance(session, TrackedSession)
    assert session.was_closed


async def test_each_owned_scope_closes_its_session(database: Database) -> None:
    factory = RepositoryFactory(repository_class=ExampleRepository, database=database)
    async with factory.open_repository() as first:
        assert_type(first, ExampleRepository)
        first_session = first.db_session
        assert isinstance(first_session, TrackedSession)
        assert not first_session.was_closed
    assert first_session.was_closed

    with pytest.raises(RuntimeError, match="operation failed"):
        async with factory.open_repository() as second:
            second_session = second.db_session
            assert isinstance(second_session, TrackedSession)
            assert second_session is not first_session
            assert not second_session.was_closed
            raise RuntimeError("operation failed")
    assert second_session.was_closed
