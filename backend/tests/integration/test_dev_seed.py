"""격리 스키마에서 개발 시드의 기간 선별·서비스 commit·재실행 보존을 확인한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, tzinfo
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.db.base import Base
from app.core.db.session import Database
from app.core.demo_data import DEV_ACCOUNT_IDS
from app.models.auth import Account
from app.models.contests import Contest
from app.models.profiles import Profile
from app.models.teams import Team
from app.repositories.contest_import import insert_contest
from app.rules.contests import interpret_deadline, interpret_opening
from app.schemas.application_create import ApplicationCreate
from app.services.application_create import submit_application
from scripts import seed_dev_data as seed

pytestmark = [pytest.mark.integration, pytest.mark.database]
NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)


@pytest_asyncio.fixture
async def seed_database(database_url: str) -> AsyncIterator[Database]:
    schema = f"dev_seed_{uuid4().hex}"
    engine = create_async_engine(
        database_url,
        execution_options={"schema_translate_map": {None: schema}},
        # validate_seed의 원시 SQL도 public이 아닌 같은 격리 스키마를 읽는다.
        connect_args={"server_settings": {"search_path": schema}},
    )
    database = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    try:
        async with engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            await connection.run_sync(Base.metadata.create_all)
        yield database
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        await engine.dispose()


@pytest.fixture
def fast_password_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hash_for_storage_only(_password: str) -> str:
        return "test-only-seed-hash-not-used-for-authentication"

    # 암호 검증은 auth 테스트가 담당한다. 여기서는 원래 300개 행의 저장을 검사한다.
    monkeypatch.setattr(seed, "hash_password", hash_for_storage_only)


@asynccontextmanager
async def seed_transaction(database: Database) -> AsyncIterator[AsyncSession]:
    # 원래 run()과 같은 외부 transaction/savepoint 경계에서 실제 서비스가 commit한다.
    async with database.engine.begin() as connection:
        async with AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as session:
            yield session


async def snapshot(database: Database) -> dict[str, list[tuple[object, ...]]]:
    async with database.session() as session:
        result = {}
        for table in Base.metadata.sorted_tables:
            rows = await session.execute(select(table).order_by(*table.primary_key))
            result[table.name] = [tuple(row) for row in rows]
        return result


async def add_contest(
    database: Database, starts_at: datetime, ends_at: datetime
) -> UUID:
    opening = interpret_opening(
        source_date=starts_at.date(),
        source_time=starts_at.time(),
        source_timezone="UTC",
    )
    closing = interpret_deadline(
        source_date=ends_at.date(),
        source_time=ends_at.time(),
        source_timezone="UTC",
    )
    identity = uuid4()
    contest = Contest(
        contest_id=identity,
        title="개발 시드 검증 공고",
        organizer_name="가상 기관",
        official_url="https://example.test/dev-seed",
        eligibility_text="격리 테스트용",
        member_limit_kind="range",
        min_members=1,
        max_members=4,
        verified_at=starts_at,
        registration_opens_at=opening.ends_at,
        registration_closes_at=closing.ends_at,
        open_source_date=opening.source_date,
        open_source_time=opening.source_time,
        open_source_timezone=opening.source_timezone,
        open_effective_timezone=opening.effective_timezone,
        open_timezone_assumed=opening.timezone_assumed,
        close_source_date=closing.source_date,
        close_source_time=closing.source_time,
        close_source_timezone=closing.source_timezone,
        close_effective_timezone=closing.effective_timezone,
        close_time_assumed=closing.time_assumed,
        close_timezone_assumed=closing.timezone_assumed,
    )
    async with database.session() as session:
        await insert_contest(
            session, contest, audiences=["unrestricted"], fields=["design"]
        )
        await session.commit()
    return identity


@pytest.mark.parametrize(
    ("starts_in", "ends_in", "eligible"),
    [
        (None, None, False),
        (timedelta(days=-2), timedelta(microseconds=-1), False),
        (timedelta(microseconds=1), timedelta(hours=2), False),
        (timedelta(0), timedelta(hours=2), True),
        (timedelta(days=-1), timedelta(hours=1, microseconds=-1), False),
        (timedelta(days=-1), timedelta(hours=1), False),
        (timedelta(days=-1), timedelta(hours=1, microseconds=1), True),
    ],
    ids=[
        "no-contest",
        "closed",
        "scheduled",
        "opening-now",
        "under-one-hour",
        "exactly-one-hour",
        "over-one-hour",
    ],
)
async def test_contest_selection_uses_opening_and_one_hour_boundaries(
    seed_database: Database,
    monkeypatch: pytest.MonkeyPatch,
    starts_in: timedelta | None,
    ends_in: timedelta | None,
    eligible: bool,
) -> None:
    class FixedClock:
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    class SelectionReached(Exception):
        pass

    monkeypatch.setattr(seed, "datetime", FixedClock)
    contest_id = None
    if starts_in is not None and ends_in is not None:
        contest_id = await add_contest(seed_database, NOW + starts_in, NOW + ends_in)
    async with seed_database.session() as session:
        # 선별이 잘못 통과하면 실제 팀 생성 분기에 도달하도록 최소 후보 8명을 둔다.
        for index, account_id in enumerate(DEV_ACCOUNT_IDS[100:108]):
            session.add(
                Account(
                    account_id=account_id,
                    login_id_normalized=f"candidate{index}",
                    password_hash="test-only",
                )
            )
            await session.flush()
            session.add(
                Profile(
                    profile_id=account_id, real_name=f"후보 {index}", is_public=True
                )
            )
        await session.commit()

    selected = []

    async def observe_selected_contest(
        _session: AsyncSession, _index: int, contest: Contest
    ) -> Team:
        selected.append(contest.contest_id)
        raise SelectionReached

    # SQL 선별 자체는 실행하고, 경계마다 팀 100개를 만드는 비용만 피한다.
    monkeypatch.setattr(seed, "seed_team", observe_selected_contest)
    async with seed_database.session() as session:
        if eligible:
            with pytest.raises(SelectionReached):
                await seed.seed_teams(session)
            assert selected == [contest_id]
        else:
            assert await seed.seed_teams(session) == 0
            assert selected == []


async def test_partial_seed_and_service_commits_roll_back_together(
    seed_database: Database,
    fast_password_hash: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    await add_contest(seed_database, now - timedelta(days=1), now + timedelta(days=30))
    before = await snapshot(seed_database)
    original_submit = submit_application
    observed = {}

    async def fail_after_service_commit(
        session: AsyncSession, account_id: UUID, team_id: UUID, body: ApplicationCreate
    ) -> None:
        await original_submit(session, account_id, team_id, body)
        observed.update(await seed.counts(session))
        raise RuntimeError("seed interrupted after service commit")

    monkeypatch.setattr(seed, "submit_application", fail_after_service_commit)
    with pytest.raises(RuntimeError, match="seed interrupted after service commit"):
        async with seed_transaction(seed_database) as session:
            assert await seed.seed_users(session) == 300
            await session.commit()
            await seed.seed_teams(session)

    assert observed["accounts"] == 300 and observed["teams"] == 2
    assert observed["applications"] == 1 and observed["notifications"] == 2
    assert await snapshot(seed_database) == before


async def test_reapplication_preserves_edited_profiles_and_all_existing_rows(
    seed_database: Database, fast_password_hash: None
) -> None:
    now = datetime.now(UTC)
    await add_contest(seed_database, now - timedelta(days=1), now + timedelta(days=30))
    async with seed_transaction(seed_database) as session:
        assert await seed.seed_users(session) == 300
        await session.commit()
        assert await seed.seed_teams(session) == 100
        await seed.validate_seed(session)
        await session.commit()

    async with seed_database.session() as session:
        profile = await session.get(Profile, DEV_ACCOUNT_IDS[0])
        assert profile is not None
        profile.real_name = "사용자가 편집한 이름"
        profile.introduction = "시드 재실행으로 덮어쓰면 안 되는 소개"
        profile.is_public = False
        profile.version += 1
        await session.commit()
    before = await snapshot(seed_database)

    async with seed_transaction(seed_database) as session:
        assert await seed.seed_users(session) == 0
        await session.commit()
        assert await seed.seed_teams(session) == 0
        await seed.validate_seed(session)
        await session.commit()

    assert len(before["accounts"]) == 300 and len(before["teams"]) == 100
    assert await snapshot(seed_database) == before
