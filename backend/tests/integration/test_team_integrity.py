"""실제 계정·공고를 참조하는 팀 저장 제약과 트랜잭션 원자성을 검증한다."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, MetaData, Table, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.base import Base
from app.core.db.session import Database
from app.models.applications import Application, ApplicationEvent
from app.models.auth import Account
from app.models.contests import Contest
from app.models.notifications import Notification
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole

pytestmark = [pytest.mark.integration, pytest.mark.database]
NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


@dataclass(frozen=True)
class TeamData:
    database: Database
    applicant_id: UUID
    leader_id: UUID
    contest_id: UUID
    other_contest_id: UUID
    team_id: UUID
    other_team_id: UUID
    application_id: UUID
    other_application_id: UUID


def contest() -> Contest:
    return Contest(
        contest_id=uuid4(),
        title="테스트 공모전",
        organizer_name="테스트 주최자",
        official_url="https://example.com/contest",
        eligibility_text="원문 참고",
        member_limit_kind="range",
        min_members=1,
        max_members=5,
        verified_at=NOW,
        registration_opens_at=NOW - timedelta(days=1),
        registration_closes_at=NOW + timedelta(days=10),
        open_source_date=date(2026, 10, 23),
        open_source_time=None,
        open_source_timezone=None,
        open_effective_timezone="Asia/Seoul",
        open_timezone_assumed=True,
        close_source_date=date(2026, 11, 3),
        close_source_time=None,
        close_source_timezone=None,
        close_effective_timezone="Asia/Seoul",
        close_time_assumed=True,
        close_timezone_assumed=True,
    )


def team(contest_id: UUID, leader_id: UUID) -> Team:
    return Team(
        team_id=uuid4(),
        request_id=uuid4(),
        request_fingerprint="a" * 64,
        contest_id=contest_id,
        leader_account_id=leader_id,
        name="테스트 팀",
        introduction="테스트에 사용하는 팀 소개입니다.",
        target_capacity=3,
        recruitment_state="open",
        closed_reason=None,
        recruitment_closes_at=NOW + timedelta(days=5),
        deadline_source_date=date(2026, 10, 29),
        deadline_source_time=None,
        deadline_source_timezone=None,
        deadline_effective_timezone="Asia/Seoul",
        deadline_time_assumed=True,
        deadline_timezone_assumed=True,
    )


def application(team_id: UUID, contest_id: UUID, applicant_id: UUID) -> Application:
    return Application(
        application_id=uuid4(),
        request_id=uuid4(),
        request_fingerprint="b" * 64,
        team_id=team_id,
        contest_id=contest_id,
        applicant_account_id=applicant_id,
        applied_role_code="DEVELOPMENT",
        status="submitted",
        submitted_at=NOW,
        status_changed_at=NOW,
        version=1,
    )


def event(data: TeamData, **changes: object) -> ApplicationEvent:
    values: dict[str, object] = {
        "application_event_id": uuid4(),
        "application_id": data.application_id,
        "team_id": data.team_id,
        "contest_id": data.contest_id,
        "applicant_account_id": data.applicant_id,
        "application_version": 1,
        "from_status": None,
        "to_status": "submitted",
        "actor_account_id": data.applicant_id,
        "reason_code": "submitted",
        "occurred_at": NOW,
    }
    values.update(changes)
    return ApplicationEvent(**values)


@pytest_asyncio.fixture
async def team_data(database_url: str) -> AsyncIterator[TeamData]:
    schema = f"wejo_team_test_{uuid4().hex}"
    engine = create_async_engine(
        database_url, execution_options={"schema_translate_map": {None: schema}}
    )
    database = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    tables = [
        cast(Table, model.__table__)
        for model in (
            Account,
            Contest,
            Team,
            TeamRecruitmentRole,
            Application,
            TeamMembership,
            ApplicationEvent,
            Notification,
        )
    ]
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(sync, tables=tables)
            )
        async with database.session() as session:
            leader = Account(
                account_id=uuid4(),
                login_id_normalized="leader",
                password_hash="test-only",
            )
            applicant = Account(
                account_id=uuid4(),
                login_id_normalized="applicant",
                password_hash="test-only",
            )
            first_contest, second_contest = contest(), contest()
            session.add_all([leader, applicant, first_contest, second_contest])
            await session.flush()
            first_team, second_team = (
                team(first_contest.contest_id, leader.account_id),
                team(first_contest.contest_id, leader.account_id),
            )
            session.add_all([first_team, second_team])
            await session.flush()
            first_application = application(
                first_team.team_id, first_contest.contest_id, applicant.account_id
            )
            second_application = application(
                second_team.team_id, first_contest.contest_id, applicant.account_id
            )
            session.add_all([first_application, second_application])
            await session.commit()
            data = TeamData(
                database,
                applicant.account_id,
                leader.account_id,
                first_contest.contest_id,
                second_contest.contest_id,
                first_team.team_id,
                second_team.team_id,
                first_application.application_id,
                second_application.application_id,
            )
        yield data
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()


async def test_current_membership_is_unique_but_ended_history_is_preserved(
    team_data: TeamData,
) -> None:
    data = team_data
    async with data.database.session() as session:
        first = TeamMembership(
            team_id=data.team_id,
            contest_id=data.contest_id,
            account_id=data.applicant_id,
            source_application_id=data.application_id,
            joined_at=NOW,
        )
        session.add(first)
        await session.flush()
        with pytest.raises(IntegrityError, match="uq_memberships_active_contest"):
            async with session.begin_nested():
                session.add(
                    TeamMembership(
                        team_id=data.other_team_id,
                        contest_id=data.contest_id,
                        account_id=data.applicant_id,
                        source_application_id=data.other_application_id,
                        joined_at=NOW,
                    )
                )
                await session.flush()
        first.ended_at = NOW + timedelta(seconds=1)
        first.end_reason = "application_canceled"
        await session.flush()
        session.add(
            TeamMembership(
                team_id=data.other_team_id,
                contest_id=data.contest_id,
                account_id=data.applicant_id,
                source_application_id=data.other_application_id,
                joined_at=NOW + timedelta(seconds=2),
            )
        )
        await session.commit()
    async with data.database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(TeamMembership)) == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TeamMembership)
                .where(TeamMembership.ended_at.is_(None))
            )
            == 1
        )


async def test_current_application_duplicate_is_rejected_but_new_attempt_is_allowed(
    team_data: TeamData,
) -> None:
    data = team_data
    async with data.database.session() as session:
        with pytest.raises(IntegrityError, match="uq_applications_current"):
            async with session.begin_nested():
                session.add(
                    application(data.team_id, data.contest_id, data.applicant_id)
                )
                await session.flush()
        original = await session.get(Application, data.application_id)
        assert original is not None
        original.status = "canceled"
        await session.flush()
        session.add(application(data.team_id, data.contest_id, data.applicant_id))
        await session.commit()


async def test_independent_connections_cannot_create_two_current_memberships(
    team_data: TeamData,
) -> None:
    data = team_data

    async def insert_membership(team_id: UUID, application_id: UUID) -> bool:
        async with data.database.session() as session:
            session.add(
                TeamMembership(
                    team_id=team_id,
                    contest_id=data.contest_id,
                    account_id=data.applicant_id,
                    source_application_id=application_id,
                    joined_at=NOW,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
            return True

    # 도메인 서비스의 잠금과 별개로 부분 UNIQUE의 최종 방어를 검사한다.
    results = await asyncio.gather(
        insert_membership(data.team_id, data.application_id),
        insert_membership(data.other_team_id, data.other_application_id),
    )
    assert sorted(results) == [False, True]
    async with data.database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(TeamMembership)) == 1
        )


async def test_composite_foreign_key_rejects_wrong_contest(team_data: TeamData) -> None:
    data = team_data
    async with data.database.session() as session:
        with pytest.raises(IntegrityError, match="fk_applications_team_context"):
            session.add(
                application(data.team_id, data.other_contest_id, data.leader_id)
            )
            await session.flush()


@pytest.mark.parametrize(
    "changes,constraint",
    [
        (
            {
                "from_status": None,
                "to_status": "rejected",
                "reason_code": "rejected",
                "application_version": 2,
            },
            "ck_application_events_transition",
        ),
        (
            {
                "from_status": "rejected",
                "to_status": "selected",
                "reason_code": "selected",
                "application_version": 2,
            },
            "ck_application_events_transition",
        ),
        (
            {
                "from_status": "submitted",
                "to_status": "discarded",
                "reason_code": "selected_elsewhere",
                "application_version": 2,
                "actor_account_id": None,
            },
            "ck_application_events_cause",
        ),
    ],
)
async def test_invalid_event_transitions_and_missing_causes_are_rejected(
    team_data: TeamData, changes: dict[str, object], constraint: str
) -> None:
    async with team_data.database.session() as session:
        with pytest.raises(IntegrityError, match=constraint):
            session.add(event(team_data, **changes))
            await session.flush()


async def test_null_reason_cannot_bypass_closed_team_or_ended_membership_check(
    team_data: TeamData,
) -> None:
    data = team_data
    async with data.database.session() as session:
        with pytest.raises(IntegrityError, match="ck_teams_closed_reason"):
            async with session.begin_nested():
                existing = await session.get(Team, data.team_id)
                assert existing is not None
                existing.recruitment_state = "closed"
                existing.closed_reason = None
                await session.flush()
        with pytest.raises(IntegrityError, match="ck_memberships_end"):
            async with session.begin_nested():
                session.add(
                    TeamMembership(
                        team_id=data.team_id,
                        contest_id=data.contest_id,
                        account_id=data.applicant_id,
                        source_application_id=data.application_id,
                        joined_at=NOW,
                        ended_at=NOW + timedelta(seconds=1),
                        end_reason=None,
                    )
                )
                await session.flush()


async def test_failed_state_transaction_rolls_back_membership_event_and_notification(
    team_data: TeamData,
) -> None:
    data = team_data
    with pytest.raises(RuntimeError, match="rollback probe"):
        async with data.database.session() as session:
            target = await session.get(Application, data.application_id)
            assert target is not None
            target.status = "selected"
            target.version = 2
            session.add(
                TeamMembership(
                    team_id=data.team_id,
                    contest_id=data.contest_id,
                    account_id=data.applicant_id,
                    source_application_id=data.application_id,
                    joined_at=NOW,
                )
            )
            selected = event(
                data,
                from_status="submitted",
                to_status="selected",
                reason_code="selected",
                application_version=2,
                actor_account_id=data.leader_id,
            )
            session.add(selected)
            await session.flush()
            session.add(
                Notification(
                    event_id=selected.application_event_id,
                    recipient_account_id=data.applicant_id,
                    kind="application_status_changed",
                )
            )
            await session.flush()
            raise RuntimeError("rollback probe")
    async with data.database.session() as session:
        target = await session.get(Application, data.application_id)
        assert (
            target is not None and target.status == "submitted" and target.version == 1
        )
        for model in (TeamMembership, ApplicationEvent, Notification):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


async def test_duplicate_notification_cannot_replace_original_read_state(
    team_data: TeamData,
) -> None:
    data = team_data
    async with data.database.session() as session:
        submitted = event(data)
        session.add(submitted)
        await session.flush()
        original = Notification(
            event_id=submitted.application_event_id,
            recipient_account_id=data.applicant_id,
            kind="application_status_changed",
            read_at=NOW,
        )
        session.add(original)
        await session.flush()
        with pytest.raises(IntegrityError, match="uq_notifications_event_recipient"):
            async with session.begin_nested():
                session.add(
                    Notification(
                        event_id=submitted.application_event_id,
                        recipient_account_id=data.applicant_id,
                        kind="application_status_changed",
                    )
                )
                await session.flush()
        await session.commit()
    async with data.database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Notification)) == 1
        assert await session.scalar(select(Notification.read_at)) == NOW


async def test_migration_matches_models_and_downgrade_preserves_parent_tables(
    database_url: str,
) -> None:
    schema = f"wejo_team_migration_{uuid4().hex}"
    administrator = create_async_engine(database_url)
    migration_engine = create_async_engine(
        database_url, connect_args={"server_settings": {"search_path": schema}}
    )
    metadata = MetaData()
    for model in (
        Account,
        Contest,
        Team,
        TeamRecruitmentRole,
        Application,
        TeamMembership,
        ApplicationEvent,
        Notification,
    ):
        cast(Table, model.__table__).to_metadata(metadata)
    script = ScriptDirectory(str(Path(__file__).parents[2] / "alembic"))
    revision = script.get_revision("20261024_05")
    assert revision is not None
    upgrade = cast(Callable[[], None], revision.module.upgrade)
    downgrade = cast(Callable[[], None], revision.module.downgrade)

    def verify(connection: Connection) -> None:
        # 선행 도메인의 실제 테이블 위에서 이 migration만 적용·복원한다.
        metadata.create_all(
            connection,
            tables=[metadata.tables["accounts"], metadata.tables["contests"]],
        )
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            upgrade()
            assert compare_metadata(context, metadata) == []
            downgrade()
        assert set(inspect(connection).get_table_names()) == {"accounts", "contests"}

    try:
        async with administrator.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
        async with migration_engine.begin() as connection:
            await connection.run_sync(verify)
    finally:
        await migration_engine.dispose()
        async with administrator.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await administrator.dispose()
