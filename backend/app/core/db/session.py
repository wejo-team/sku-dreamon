from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@dataclass(frozen=True)
class Database:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


def create_database(url: str) -> Database:
    engine = create_async_engine(url, pool_pre_ping=True)
    return Database(
        engine=engine,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )
