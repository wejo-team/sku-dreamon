"""호출자가 선택한 읽기 스냅샷과 PostgreSQL 읽기 전용 모드를 검증한다."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db.session import begin_read_snapshot, create_database

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest.mark.parametrize("read_only", [False, True])
async def test_snapshot_keeps_rows_and_optional_read_only_mode(
    database_url: str, read_only: bool
) -> None:
    database = create_database(database_url)
    schema = f"wejo_snapshot_{uuid4().hex}"
    try:
        async with database.engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
            await connection.execute(text(f"CREATE TABLE {schema}.probe (value int)"))
            await connection.execute(text(f"INSERT INTO {schema}.probe VALUES (1)"))

        async with database.session() as session:
            await begin_read_snapshot(session, read_only=read_only)
            assert await session.scalar(text("SHOW transaction_isolation")) == (
                "repeatable read"
            )
            assert await session.scalar(text("SHOW transaction_read_only")) == (
                "on" if read_only else "off"
            )
            assert await session.scalar(text(f"SELECT value FROM {schema}.probe")) == 1
            async with database.engine.begin() as connection:
                await connection.execute(text(f"UPDATE {schema}.probe SET value = 2"))
            assert await session.scalar(text(f"SELECT value FROM {schema}.probe")) == 1
            if read_only:
                with pytest.raises(DBAPIError, match="read-only transaction"):
                    await session.execute(
                        text(f"INSERT INTO {schema}.probe VALUES (3)")
                    )
            await session.rollback()
            assert await session.scalar(text(f"SELECT value FROM {schema}.probe")) == 2
    finally:
        async with database.engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await database.engine.dispose()
