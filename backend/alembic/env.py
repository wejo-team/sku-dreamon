"""공통 ORM metadata와 비동기 DB 연결로 Alembic 실행 환경을 구성한다."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.core.db.base import Base
from app.models import academic_units as catalog_models  # noqa: F401 -- 학사 모델 등록
from app.models import auth as auth_models  # noqa: F401 -- metadata 모델 등록
from app.models import contests as contest_models  # noqa: F401 -- 공고 모델 등록

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 도메인 모델을 import하여 실제 migration 대상 metadata에 포함한다.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(Settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(str(Settings().database_url), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
