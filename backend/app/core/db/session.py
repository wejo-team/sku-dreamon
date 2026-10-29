"""비동기 DB 연결과 세션 수명을 관리하는 공통 기반을 제공한다."""

import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import Settings


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


def create_engine(settings: Settings, *, pooled: bool = True) -> AsyncEngine:
    """앱·CLI·migration에 동일한 TLS 검증과 유한 I/O 예산을 적용한다."""
    tls = None
    if settings.database_tls_ca_file is not None:
        tls = ssl.create_default_context(cafile=str(settings.database_tls_ca_file))
        tls.verify_mode = ssl.CERT_REQUIRED
        tls.check_hostname = True
    connect_args: dict[str, object] = {
        "timeout": settings.database_connect_timeout_seconds,
        "command_timeout": settings.database_command_timeout_seconds,
        "server_settings": {
            "statement_timeout": str(
                int(settings.database_statement_timeout_seconds * 1000)
            ),
            "lock_timeout": str(int(settings.database_lock_timeout_seconds * 1000)),
            "idle_in_transaction_session_timeout": str(
                int(settings.database_idle_transaction_timeout_seconds * 1000)
            ),
        },
    }
    if tls is not None:
        connect_args["ssl"] = tls
    if not pooled:
        return create_async_engine(
            str(settings.database_url),
            connect_args=connect_args,
            poolclass=NullPool,
            hide_parameters=True,
        )
    return create_async_engine(
        str(settings.database_url),
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        hide_parameters=True,
    )


def create_database(url: str, *, settings: Settings | None = None) -> Database:
    config = settings or Settings(database_url=PostgresDsn(url), _env_file=None)
    if str(config.database_url) != str(PostgresDsn(url)):
        raise ValueError("Database URL must match validated settings")
    engine = create_engine(config)
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
