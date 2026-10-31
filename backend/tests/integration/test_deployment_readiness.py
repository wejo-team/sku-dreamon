"""격리 PostgreSQL에서 revision·서버 timeout·행 잠금 예산을 검증한다."""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import PostgresDsn, SecretStr
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.core.db.session import Database, create_database
from app.security.passwords import PasswordBlocklist
from app.services.health import ReadinessProbe, is_ready

pytestmark = [pytest.mark.integration, pytest.mark.database]


def settings_and_blocklist(
    database_url: str, tmp_path: Path
) -> tuple[Settings, PasswordBlocklist]:
    path = tmp_path / "synthetic-blocklist.txt"
    path.write_text("synthetic-blocked-password\n")
    settings = Settings(
        database_url=PostgresDsn(database_url),
        csrf_signing_key=SecretStr("synthetic-test-signing-key-at-least-32-bytes"),
        auth_allowed_origins=("https://www.example.com",),
        password_blocklist_path=path,
        password_blocklist_version="synthetic-v1",
        _env_file=None,
    )
    return settings, PasswordBlocklist.from_file(path, version="synthetic-v1")


@pytest.mark.parametrize(
    "revision", ["20261026_09", "20261031_10", "future-unapproved", None]
)
async def test_real_database_schema_compatibility(
    database_url: str, tmp_path: Path, revision: str | None
) -> None:
    settings, blocklist = settings_and_blocklist(database_url, tmp_path)
    database = create_database(database_url, settings=settings)
    try:
        async with database.engine.connect() as connection:
            transaction = await connection.begin()
            try:
                schema = f"ready_test_{uuid4().hex}"
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                if revision is not None:
                    await connection.execute(
                        text(
                            "CREATE TABLE alembic_version "
                            "(version_num varchar(32) primary key)"
                        )
                    )
                    await connection.execute(
                        text("INSERT INTO alembic_version VALUES (:revision)"),
                        {"revision": revision},
                    )
                bound = Database(
                    database.engine,
                    async_sessionmaker(
                        connection,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    ),
                )
                assert await is_ready(
                    settings, bound, blocklist, None, ReadinessProbe()
                ) is (revision in {"20261026_09", "20261031_10"})
            finally:
                await transaction.rollback()
    finally:
        await database.engine.dispose()


async def test_postgresql_statement_and_lock_budgets(database_url: str) -> None:
    settings = Settings(
        database_url=PostgresDsn(database_url),
        database_statement_timeout_seconds=0.1,
        database_lock_timeout_seconds=0.1,
        _env_file=None,
    )
    database = create_database(database_url, settings=settings)
    try:
        async with database.session() as session:
            assert await session.scalar(text("SHOW statement_timeout")) == "100ms"
            assert await session.scalar(text("SHOW lock_timeout")) == "100ms"
            assert (
                await session.scalar(text("SHOW idle_in_transaction_session_timeout"))
                == "15s"
            )
            async with asyncio.timeout(1):
                with pytest.raises(DBAPIError):
                    await session.execute(text("SELECT pg_sleep(2)"))
            await session.rollback()
    finally:
        await database.engine.dispose()


async def test_postgresql_row_lock_wait_is_finite(database_url: str) -> None:
    settings = Settings(
        database_url=PostgresDsn(database_url),
        database_lock_timeout_seconds=0.1,
        _env_file=None,
    )
    database = create_database(database_url, settings=settings)
    schema = f"lock_test_{uuid4().hex}"
    try:
        async with database.engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(
                text(
                    f'CREATE TABLE "{schema}".locks '
                    "(id integer primary key, value integer)"
                )
            )
            await connection.execute(
                text(f'INSERT INTO "{schema}".locks VALUES (1, 0)')
            )
        async with database.session() as owner, database.session() as contender:
            await owner.execute(
                text(f'SELECT * FROM "{schema}".locks WHERE id = 1 FOR UPDATE')
            )
            async with asyncio.timeout(1):
                with pytest.raises(DBAPIError):
                    await contender.execute(
                        text(f'UPDATE "{schema}".locks SET value = 1 WHERE id = 1')
                    )
            await contender.rollback()
            await owner.rollback()
    finally:
        async with database.engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await database.engine.dispose()


async def test_readiness_has_a_total_pool_acquisition_budget(
    database_url: str, tmp_path: Path
) -> None:
    settings, blocklist = settings_and_blocklist(database_url, tmp_path)
    settings.database_pool_size = 1
    settings.database_max_overflow = 0
    settings.readiness_timeout_seconds = 0.1
    database = create_database(database_url, settings=settings)
    probe = ReadinessProbe()
    try:
        async with database.engine.connect():
            async with asyncio.timeout(0.5):
                assert not await is_ready(settings, database, blocklist, None, probe)
        assert await probe.close(0.5)
        assert await is_ready(settings, database, blocklist, None, ReadinessProbe())
    finally:
        await probe.close(0.5)
        await database.engine.dispose()
