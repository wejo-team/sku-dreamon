"""격리 스키마에서 개발 시드의 기간 선별·서비스 commit·재실행 보존을 확인한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta, tzinfo
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.db.base import Base
from app.core.db.session import Database
from app.core.demo_data import DEV_ACCOUNT_IDS
from app.models.applications import Application
from app.models.auth import Account
from app.models.contests import Contest
from app.models.profiles import Profile
from app.models.teams import Team, TeamRecruitmentRole
from app.repositories.contest_import import insert_contest
from app.rules.catalogs import RoleCode
from app.rules.contests import interpret_deadline, interpret_opening
from app.schemas.application_create import ApplicationCreate
from app.services.application_create import submit_application
from scripts import seed_dev_data as seed
from scripts import seed_e2e_data
from scripts.dev_dataset import ContestCandidate, DatasetPlan

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


@pytest.mark.parametrize("incomplete", [False, True])
async def test_e2e_fixture_follows_team_plan_and_rolls_back_incomplete_seed(
    seed_database: Database,
    database_url: str,
    fast_password_hash: None,
    monkeypatch: pytest.MonkeyPatch,
    incomplete: bool,
) -> None:
    # URL 차단은 test_e2e_tools에서 검증한다. 이 테스트는 별도 *_test DB의
    # 격리 스키마에 실제 E2E transaction·서비스 commit 경계를 실행한다.
    monkeypatch.setattr(
        seed_e2e_data, "validate_target", lambda _: make_url(database_url)
    )
    monkeypatch.setattr(seed_e2e_data, "create_database", lambda _: seed_database)
    before = await snapshot(seed_database)
    if incomplete:

        async def seed_one_pair(
            session: AsyncSession, plan: DatasetPlan | None = None
        ) -> int:
            # 서비스 commit 이후에도 불완전한 결과를 감지하면 전체를 되돌린다.
            assert plan is not None
            return await seed.seed_teams(
                session, replace(plan, assignments=plan.assignments[:1])
            )

        monkeypatch.setattr(seed_e2e_data, "seed_teams", seed_one_pair)
        with pytest.raises(seed_e2e_data.FixtureError, match="complete E2E fixture"):
            await seed_e2e_data.run(database_url, apply=True)
        assert await snapshot(seed_database) == before
        return

    result = await seed_e2e_data.run(database_url, apply=True)
    assert result["status"] == "applied"
    async with seed_database.session() as session:
        actual = await seed.counts(session)
        assert actual["contests"] == 13
        assert actual["accounts"] == 300
        # 접수 중 11개 공고 × 최대 6팀. 12+1 공고 페이지와 팀 2페이지를 유지한다.
        assert actual["teams"] == 66
        assert result["counts"] == actual
        assert set(await session.scalars(select(TeamRecruitmentRole.role_code))) == {
            code.value for code in RoleCode
        }
        assert set(await session.scalars(select(Application.status))) == {
            "submitted",
            "reviewing",
            "rejected",
            "canceled",
            "selected",
            "discarded",
        }


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
        (timedelta(microseconds=1), timedelta(days=8), False),
        (timedelta(0), timedelta(days=8), True),
        (timedelta(days=-1), timedelta(days=7, microseconds=-1), False),
        (timedelta(days=-1), timedelta(days=7), True),
        (timedelta(days=-1), timedelta(days=7, microseconds=1), True),
    ],
    ids=[
        "no-contest",
        "closed",
        "scheduled",
        "opening-now",
        "under-seven-days",
        "exactly-seven-days",
        "over-seven-days",
    ],
)
async def test_contest_selection_uses_opening_and_seven_day_boundaries(
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
        _session: AsyncSession,
        _index: int,
        contest: ContestCandidate,
        _reference_at: datetime,
    ) -> Team:
        selected.append(contest.contest_id)
        raise SelectionReached

    # DB 조회·계획 선별은 실행하고 경계마다 지원·알림을 만드는 비용만 피한다.
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
        assert await seed.seed_teams(session) == 6
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

    assert len(before["accounts"]) == 300 and len(before["teams"]) == 6
    assert await snapshot(seed_database) == before


async def populate_legacy_seed(
    database: Database, monkeypatch: pytest.MonkeyPatch, *, teams: bool = False
) -> None:
    from scripts.seed_content import legacy_profile_input, legacy_team_content

    def legacy_story(
        index: int, contest: ContestCandidate
    ) -> tuple[str, str, tuple[str, ...]]:
        name, introduction = legacy_team_content(index, contest.title)
        roles = list(RoleCode)
        return (
            name,
            introduction,
            (roles[index % 6].value, roles[(index + 1) % 6].value),
        )

    if teams:
        now = datetime.now(UTC)
        await add_contest(database, now - timedelta(days=1), now + timedelta(days=30))
    with monkeypatch.context() as scoped:
        scoped.setattr(seed, "profile_input", legacy_profile_input)
        scoped.setattr(seed, "team_story", legacy_story)
        async with seed_transaction(database) as session:
            assert await seed.seed_users(session) == 300
            await session.commit()
            if teams:
                assert await seed.seed_teams(session) == 6
                await seed.validate_seed(session)
                await session.commit()


async def test_refresh_only_exact_legacy_content_and_preserves_other_rows(
    seed_database: Database,
    fast_password_hash: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.demo_data import DEV_TEAM_IDS
    from app.models.profiles import PortfolioLink, ProfileSkill
    from app.models.teams import TeamRecruitmentRole

    await populate_legacy_seed(seed_database, monkeypatch, teams=True)
    async with seed_database.session() as session:
        profiles = []
        for identity in DEV_ACCOUNT_IDS[:8]:
            profile = await session.get(Profile, identity)
            assert profile is not None
            profiles.append(profile)
        profiles[0].real_name = "사용자가 고친 이름"
        portfolio = await session.get(PortfolioLink, DEV_ACCOUNT_IDS[1])
        assert portfolio
        portfolio.title = "사용자가 고친 포트폴리오"
        session.add(ProfileSkill(account_id=DEV_ACCOUNT_IDS[2], skill_code="ui_ux"))
        profiles[3].is_public = not profiles[3].is_public
        profiles[4].academic_unit_id = profiles[3].academic_unit_id
        profiles[5].version += 1  # 값을 되돌렸어도 편집 이력을 덮지 않는다.
        profiles[6].introduction = "직접 작성한 소개"
        profiles[7].weekly_availability_code = None
        teams = []
        for identity in DEV_TEAM_IDS[:4]:
            team = await session.get(Team, identity)
            assert team is not None
            teams.append(team)
        teams[0].name = "직접 고친 팀명"
        teams[1].introduction = "직접 고친 팀 소개"
        session.add(TeamRecruitmentRole(team_id=DEV_TEAM_IDS[2], role_code="planning"))
        teams[3].target_capacity += 1
        await session.commit()
    before = await snapshot(seed_database)

    # 기존 일반 재실행은 새로운 문구를 적용하지 않고 모든 기존 행을 보존한다.
    async with seed_transaction(seed_database) as session:
        assert await seed.seed_users(session) == 0
        assert await seed.seed_teams(session) == 0
        await session.commit()
    assert await snapshot(seed_database) == before

    # run()과 같은 외부 rollback: 미리보기 중 버전·포트폴리오도 저장되지 않는다.
    async with seed_database.engine.connect() as connection:
        async with connection.begin() as transaction:
            async with AsyncSession(
                bind=connection, join_transaction_mode="create_savepoint"
            ) as session:
                result = await seed.refresh_content(session)
                assert result == {
                    "profilesUpdated": 292,
                    "profilesSkipped": 8,
                    "profilesMissing": 0,
                    "teamsUpdated": 2,
                    "teamsSkipped": 4,
                    "teamsMissing": 94,
                }
                await session.commit()
            await transaction.rollback()
    assert await snapshot(seed_database) == before

    # 프로필과 첫 팀의 변경 뒤 실패해도 같은 외부 transaction이 전부 되돌린다.
    original_content = seed.team_content
    attempts = 0

    def fail_during_team_refresh(index: int, title: str) -> tuple[str, str]:
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("during team refresh")
        return original_content(index, title)

    with monkeypatch.context() as scoped:
        scoped.setattr(seed, "team_content", fail_during_team_refresh)
        with pytest.raises(RuntimeError, match="during team refresh"):
            async with seed_transaction(seed_database) as session:
                await seed.refresh_content(session)
    assert attempts == 2
    assert await snapshot(seed_database) == before

    async with seed_transaction(seed_database) as session:
        assert await seed.refresh_content(session) == result
        await seed.validate_seed(session)
        await session.commit()
    after = await snapshot(seed_database)
    for table, rows in before.items():
        if table not in {"profiles", "portfolio_links", "teams"}:
            assert after[table] == rows, table
    async with seed_database.session() as session:
        for index, identity in enumerate(DEV_ACCOUNT_IDS):
            profile = await session.get(Profile, identity)
            assert profile
            original = next(row for row in before["profiles"] if row[0] == identity)
            if index < 8:
                assert (
                    tuple(
                        (
                            await session.execute(
                                select(Profile.__table__).where(
                                    Profile.profile_id == identity
                                )
                            )
                        ).one()
                    )
                    == original
                )
            else:
                assert profile.real_name.endswith(f"[테스트 P{index + 1:03d}]")
                assert profile.version == 2
        for index, identity in enumerate(DEV_TEAM_IDS[:6]):
            row = (
                await session.execute(
                    select(Team.__table__).where(Team.team_id == identity)
                )
            ).one()
            original = next(old for old in before["teams"] if old[0] == identity)
            if index < 4:
                assert tuple(row) == original
            else:
                current = row._mapping
                old = dict(zip(Team.__table__.columns.keys(), original, strict=True))
                assert current["name"].endswith(f"[테스트 T{index + 1:03d}]")
                assert isinstance(old["version"], int)
                assert current["version"] == old["version"] + 1
                for field in current:
                    if field not in {"name", "introduction", "version", "updated_at"}:
                        assert current[field] == old[field]
    async with seed_transaction(seed_database) as session:
        repeated = await seed.refresh_content(session)
        assert repeated["profilesUpdated"] == repeated["teamsUpdated"] == 0
        await session.commit()
    assert await snapshot(seed_database) == after


async def test_refresh_failure_rolls_back_content_and_versions(
    seed_database: Database,
    fast_password_hash: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await populate_legacy_seed(seed_database, monkeypatch)
    before = await snapshot(seed_database)
    with pytest.raises(RuntimeError, match="after refresh"):
        async with seed_transaction(seed_database) as session:
            refreshed = await seed.refresh_content(session, users_only=True)
            assert refreshed["profilesUpdated"] == 300
            await session.commit()
            raise RuntimeError("after refresh")
    assert await snapshot(seed_database) == before


async def test_refresh_rechecks_after_waiting_for_profile_writer(
    seed_database: Database,
    fast_password_hash: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from app.repositories.profile_write import lock_profile
    from app.repositories.recruitment_locks import lock_accounts

    await populate_legacy_seed(seed_database, monkeypatch)
    entered = asyncio.Event()

    async def observe_lock(session: AsyncSession, identities: object) -> None:
        entered.set()
        await lock_accounts(session, DEV_ACCOUNT_IDS)

    monkeypatch.setattr(seed, "lock_accounts", observe_lock)
    async with seed_database.session() as writer, seed_database.session() as updater:
        cached = await updater.get(Profile, DEV_ACCOUNT_IDS[0])
        assert cached and cached.version == 1
        await lock_accounts(writer, [DEV_ACCOUNT_IDS[0]])
        profile = await lock_profile(writer, DEV_ACCOUNT_IDS[0])
        assert profile
        profile.introduction = "갱신 미리보기와 경쟁한 사용자 편집"
        profile.version += 1
        pending = asyncio.create_task(seed.refresh_content(updater, users_only=True))
        await entered.wait()
        await writer.commit()
        result = await asyncio.wait_for(pending, timeout=15)
        await updater.commit()
        assert result["profilesUpdated"] == 299
        assert result["profilesSkipped"] == 1
    async with seed_database.session() as session:
        saved = await session.get(Profile, DEV_ACCOUNT_IDS[0])
        assert saved and saved.introduction == "갱신 미리보기와 경쟁한 사용자 편집"
        assert saved.version == 2 and "[테스트" not in saved.real_name


async def test_refresh_skips_uuid_login_collision_without_weakening_regular_seed(
    seed_database: Database,
    fast_password_hash: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await populate_legacy_seed(seed_database, monkeypatch)
    async with seed_database.session() as session:
        account = await session.get(Account, DEV_ACCOUNT_IDS[0])
        assert account
        account.login_id_normalized = "differentowner"
        await session.commit()
    before = await snapshot(seed_database)
    async with seed_transaction(seed_database) as session:
        with pytest.raises(ValueError, match="UUID"):
            await seed.seed_users(session)
    assert await snapshot(seed_database) == before
    async with seed_transaction(seed_database) as session:
        result = await seed.refresh_content(session, users_only=True)
        assert result["profilesUpdated"] == 299
        assert result["profilesSkipped"] == 1
        await session.commit()
    async with seed_database.session() as session:
        profile = await session.get(Profile, DEV_ACCOUNT_IDS[0])
        assert profile and profile.version == 1 and profile.real_name == "김민준"
