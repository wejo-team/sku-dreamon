"""실제 PostgreSQL에서 공고 migration·행 제약·분류 참조 무결성을 검증한다."""

import importlib.util
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time
from pathlib import Path
from types import ModuleType
from typing import cast
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, Table, delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateSchema

from app.core.db.base import Base
from app.core.db.session import create_database
from app.domains.contests.models import Contest, ContestAudience, ContestField

pytestmark = [pytest.mark.integration, pytest.mark.database]


def load_migration() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2] / "alembic/versions/20261024_02_contests.py"
    )
    spec = importlib.util.spec_from_file_location("contest_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migration(connection: Connection, *, downgrade: bool = False) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        migration = load_migration()
        if downgrade:
            migration.downgrade()
        else:
            migration.upgrade()


@pytest_asyncio.fixture
async def session(
    database_url: str, request: pytest.FixtureRequest
) -> AsyncIterator[AsyncSession]:
    database = create_database(database_url)
    schema = f"contest_test_{uuid4().hex}"
    try:
        async with database.engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(CreateSchema(schema))
                await connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                if getattr(request, "param", "migration") == "models":
                    tables = [
                        cast(Table, model.__table__)
                        for model in (Contest, ContestAudience, ContestField)
                    ]
                    await connection.run_sync(
                        lambda conn: Base.metadata.create_all(conn, tables=tables)
                    )
                else:
                    await connection.run_sync(run_migration)
                async with AsyncSession(
                    connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session
            finally:
                await transaction.rollback()
    finally:
        await database.engine.dispose()


def new_contest(**overrides: object) -> Contest:
    values: dict[str, object] = {
        "title": "공고 테스트",
        "organizer_name": "테스트 기관",
        "official_url": "https://example.org/contest",
        "eligibility_text": "원문에서 참가 조건을 확인해 주세요.",
        "member_limit_kind": "range",
        "min_members": 1,
        "max_members": 4,
        "verified_at": datetime(2026, 10, 1, tzinfo=UTC),
        "registration_opens_at": datetime(2026, 10, 1, tzinfo=UTC),
        "registration_closes_at": datetime(2026, 10, 21, 15, tzinfo=UTC),
        "open_source_date": date(2026, 10, 1),
        "open_source_time": time(9),
        "open_source_timezone": "Asia/Seoul",
        "open_effective_timezone": "Asia/Seoul",
        "open_timezone_assumed": False,
        "close_source_date": date(2026, 10, 21),
        "close_source_time": None,
        "close_source_timezone": None,
        "close_effective_timezone": "Asia/Seoul",
        "close_time_assumed": True,
        "close_timezone_assumed": True,
    }
    return Contest(**(values | overrides))


async def test_migration_stores_original_metadata_and_server_defaults(
    session: AsyncSession,
) -> None:
    contest = new_contest()
    session.add(contest)
    await session.flush()
    session.add_all(
        [
            ContestAudience(contest_id=contest.contest_id, audience_code="student"),
            ContestField(contest_id=contest.contest_id, field_code="it_technology"),
        ]
    )
    await session.commit()
    await session.refresh(contest)

    assert contest.version == 1
    assert contest.created_at == contest.updated_at
    assert contest.poster_url is None
    assert contest.open_source_time == time(9)
    assert contest.close_source_time is None
    assert contest.close_time_assumed and contest.close_timezone_assumed
    assert contest.registration_closes_at == datetime(2026, 10, 21, 15, tzinfo=UTC)
    assert await session.scalar(select(ContestAudience.audience_code)) == "student"
    assert await session.scalar(select(ContestField.field_code)) == "it_technology"


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": " \t\n"},
        {"organizer_name": " "},
        {"eligibility_text": ""},
        {"official_url": "\n"},
        {"member_limit_kind": "other"},
        {"min_members": None},
        {"max_members": None},
        {"min_members": 0},
        {"min_members": 5, "max_members": 4},
        {"member_limit_kind": "unknown", "min_members": 1, "max_members": None},
        {"member_limit_kind": "unlimited", "max_members": 4},
        {"registration_closes_at": datetime(2026, 10, 1, tzinfo=UTC)},
        {"close_time_assumed": False},
        {"close_timezone_assumed": False},
        {"open_timezone_assumed": True},
        {"version": 0},
    ],
)
async def test_database_rejects_invalid_contest_rows(
    session: AsyncSession, overrides: dict[str, object]
) -> None:
    session.add(new_contest(**overrides))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()
    assert await session.scalar(select(Contest.contest_id)) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"member_limit_kind": "unlimited", "min_members": None, "max_members": None},
        {"member_limit_kind": "unlimited", "min_members": 2, "max_members": None},
        {"member_limit_kind": "unknown", "min_members": None, "max_members": None},
        {"min_members": 9223372036854775807, "max_members": 9223372036854775807},
    ],
)
async def test_database_preserves_capacity_conditions(
    session: AsyncSession, overrides: dict[str, object]
) -> None:
    contest = new_contest(**overrides)
    session.add(contest)
    await session.flush()
    await session.refresh(contest)
    for name, value in overrides.items():
        assert getattr(contest, name) == value


async def test_classification_keys_and_restrict_foreign_keys(
    session: AsyncSession,
) -> None:
    contest = new_contest()
    session.add(contest)
    await session.flush()
    session.add(ContestAudience(contest_id=contest.contest_id, audience_code="student"))
    await session.flush()

    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(
                ContestAudience(contest_id=contest.contest_id, audience_code="other")
            )
            await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(
                ContestAudience(contest_id=contest.contest_id, audience_code="student")
            )
            await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(ContestField(contest_id=uuid4(), field_code="it_technology"))
            await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(
                delete(Contest).where(Contest.contest_id == contest.contest_id)
            )


async def test_migration_downgrade_removes_only_its_tables(
    session: AsyncSession,
) -> None:
    connection = await session.connection()
    await connection.run_sync(lambda conn: run_migration(conn, downgrade=True))
    tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
    assert not {"contests", "contest_fields", "contest_audiences"}.intersection(tables)


@pytest.mark.parametrize(
    "column", ["title", "organizer_name", "eligibility_text", "official_url"]
)
@pytest.mark.parametrize("whitespace", ["\u00a0", "\u2007"])
async def test_database_rejects_unicode_whitespace_only_required_text(
    session: AsyncSession, column: str, whitespace: str
) -> None:
    session.add(new_contest(**{column: whitespace}))
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.parametrize("session", ["migration", "models"], indirect=True)
async def test_required_text_matches_python_whitespace_without_rewriting_content(
    session: AsyncSession,
) -> None:
    whitespace = [chr(code) for code in range(0x110000) if chr(code).isspace()]
    for character in whitespace:
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(new_contest(title=character))
                await session.flush()

    original = "\u00a0공고 이름\u2007"
    contest = new_contest(title=original)
    session.add(contest)
    await session.flush()
    await session.refresh(contest)
    assert contest.title == original
