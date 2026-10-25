"""비동기 DB 연결과 세션 수명을 관리하는 공통 기반을 제공한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@dataclass(frozen=True)
class Database:
    """애플리케이션이 공유하는 엔진과 사용 범위별 세션을 제공한다."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """독립된 세션을 제공하고 사용 범위가 끝나면 정리한다.

        저장 확정은 호출자가 명시적으로 수행하며, 정리 시 미커밋 변경은
        롤백된다.
        """
        async with self.session_factory() as session:
            yield session


def create_database(url: str) -> Database:
    engine = create_async_engine(url, pool_pre_ping=True)
    return Database(
        engine=engine,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )


async def begin_read_snapshot(
    session: AsyncSession, *, read_only: bool = False
) -> None:
    """호출자가 첫 DB 접근 전에 선택한 읽기 트랜잭션 설정을 적용한다."""
    await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    if read_only:
        await session.execute(text("SET TRANSACTION READ ONLY"))
