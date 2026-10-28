"""격리 PostgreSQL에서 포스터만 보완하고 동시 변경·실패를 원자적으로 보호한다."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.db.base import Base
from app.core.db.session import Database
from app.models.contests import Contest
from scripts.backfill_contest_posters import (
    BackfillError,
    Decision,
    apply_changes,
    snapshot,
)
from scripts.seed_e2e_data import build_contests

pytestmark = [pytest.mark.integration, pytest.mark.database]
POSTER = "https://api.linkareer.com/attachments/456"


@pytest_asyncio.fixture
async def database(database_url: str) -> AsyncIterator[Database]:
    schema = f"poster_backfill_{uuid4().hex}"
    engine = create_async_engine(
        database_url, execution_options={"schema_translate_map": {None: schema}}
    )
    database = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    try:
        async with engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(
                    conn, tables=[cast(Table, Contest.__table__)]
                )
            )
        async with database.session() as session, session.begin():
            for index, (contest, _) in enumerate(build_contests(datetime.now(UTC))[:2]):
                contest.contest_id = UUID(int=index + 1)
                contest.source_url = f"https://linkareer.com/activity/{index + 123}"
                session.add(contest)
        yield database
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


async def proposals(database: Database) -> list[Decision]:
    async with database.session() as session:
        rows = await session.scalars(select(Contest).order_by(Contest.contest_id))
        return [
            Decision(
                before=snapshot(row),
                status="ready",
                poster_url=POSTER,
                final_image_url="https://media-cdn.linkareer.com/activity_manager/posters/456",
                content_type="image/png",
                content_length=2048,
                html_sha256="a" * 64,
                checked_at=datetime.now(UTC),
            )
            for row in rows
        ]


async def test_success_changes_only_poster_version_and_updated_at(
    database: Database,
) -> None:
    decisions = await proposals(database)
    async with database.session() as session:
        before = {
            row.contest_id: {
                c.name: getattr(row, c.name) for c in Contest.__table__.columns
            }
            for row in await session.scalars(select(Contest))
        }
    async with database.session() as session, session.begin():
        recovery = await apply_changes(session, decisions)
        assert len(recovery) == 2
        assert all(item["restore_poster_url"] is None for item in recovery)
    async with database.session() as session:
        for row in await session.scalars(select(Contest)):
            assert row.poster_url == POSTER and row.version == 2
            for column in Contest.__table__.columns:
                if column.name not in {"poster_url", "version", "updated_at"}:
                    assert (
                        getattr(row, column.name) == before[row.contest_id][column.name]
                    )


@pytest.mark.parametrize(
    "changed", ["title", "source_url", "version", "source_metadata", "poster_url"]
)
async def test_concurrent_change_rejects_whole_plan_without_touching_other_rows(
    database: Database,
    changed: str,
) -> None:
    decisions = await proposals(database)
    async with database.session() as session, session.begin():
        contest = await session.get(Contest, UUID(int=2))
        assert contest is not None
        values: dict[str, object] = {
            "title": "다른 작성자가 수정한 제목",
            "source_url": "https://linkareer.com/activity/999",
            "version": 2,
            "source_metadata": {"raw": "new source evidence"},
            "poster_url": "https://api.linkareer.com/attachments/999",
        }
        setattr(contest, changed, values[changed])
    with pytest.raises(BackfillError, match="stale_or_changed_contest"):
        async with database.session() as session, session.begin():
            await apply_changes(session, decisions)
    async with database.session() as session:
        untouched = await session.get(Contest, UUID(int=1))
        changed_row = await session.get(Contest, UUID(int=2))
        assert untouched is not None and changed_row is not None
        assert untouched.poster_url is None and untouched.version == 1
        assert getattr(changed_row, changed) == values[changed]


async def test_failure_after_flush_rolls_back_every_proposed_poster(
    database: Database,
) -> None:
    decisions = await proposals(database)
    with pytest.raises(RuntimeError, match="injected"):
        async with database.session() as session, session.begin():
            await apply_changes(session, decisions)
            raise RuntimeError("injected before transaction commit")
    async with database.session() as session:
        rows = list(await session.scalars(select(Contest)))
        assert len(rows) == 2
        assert all(row.poster_url is None and row.version == 1 for row in rows)
