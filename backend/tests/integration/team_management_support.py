"""팀 관리·현재 소속 테스트에 격리된 실제 스키마와 최소 생성 함수를 제공한다."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db.base import Base
from app.core.db.session import Database
from app.models import academic_units as catalog_models  # noqa: F401 -- 프로필 FK 등록
from app.models import notifications as notification_models  # noqa: F401 -- 실제 스키마 등록
from app.models.applications import Application
from app.models.auth import Account
from app.models.contests import Contest, ContestAudience, ContestField
from app.models.profiles import (
    PortfolioLink,
    Profile,
    ProfileDesiredRole,
    ProfileInterest,
)
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole

NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


@pytest_asyncio.fixture
async def management_database(database_url: str) -> AsyncIterator[Database]:
    schema = f"wejo_team_management_{uuid4().hex}"
    engine = create_async_engine(
        database_url,
        execution_options={"schema_translate_map": {None: schema}},
        connect_args={"server_settings": {"application_name": schema}},
    )
    database = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
            await connection.run_sync(Base.metadata.create_all)
        yield database
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()


async def seed_account(
    session: AsyncSession,
    *,
    real_name: str = "테스트 회원",
    is_public: bool = False,
) -> Account:
    account = Account(
        account_id=uuid4(),
        login_id_normalized=f"user{uuid4().hex[:16]}",
        password_hash="test-only-not-a-real-password-hash",
    )
    session.add(account)
    await session.flush()
    session.add(
        Profile(
            profile_id=account.account_id,
            real_name=real_name,
            is_public=is_public,
            experience_state="provided",
            experience_body="전체 프로필에서만 공개하는 경험",
            introduction="테스트 회원의 소개",
        )
    )
    await session.flush()
    session.add_all(
        [
            ProfileInterest(account_id=account.account_id, field_code="it_technology"),
            ProfileDesiredRole(account_id=account.account_id, role_code="development"),
            PortfolioLink(
                portfolio_link_id=account.account_id,
                url="https://example.com/private-portfolio",
                title="포트폴리오",
            ),
        ]
    )
    await session.flush()
    return account


async def seed_contest(session: AsyncSession) -> Contest:
    opens_at, closes_at = NOW - timedelta(days=1), NOW + timedelta(days=30)
    contest = Contest(
        contest_id=uuid4(),
        title="테스트 공모전",
        organizer_name="테스트 주최자",
        official_url="https://example.com/contest",
        eligibility_text="원문 참고",
        member_limit_kind="range",
        min_members=1,
        max_members=10,
        verified_at=NOW,
        registration_opens_at=opens_at,
        registration_closes_at=closes_at,
        open_source_date=opens_at.date(),
        open_source_time=None,
        open_source_timezone=None,
        open_effective_timezone="Asia/Seoul",
        open_timezone_assumed=True,
        close_source_date=closes_at.date(),
        close_source_time=None,
        close_source_timezone=None,
        close_effective_timezone="Asia/Seoul",
        close_time_assumed=True,
        close_timezone_assumed=True,
    )
    session.add(contest)
    await session.flush()
    session.add_all(
        [
            ContestAudience(contest_id=contest.contest_id, audience_code="student"),
            ContestField(contest_id=contest.contest_id, field_code="it_technology"),
        ]
    )
    await session.flush()
    return contest


async def seed_team(
    session: AsyncSession,
    contest: Contest,
    leader: Account,
    *,
    capacity: int = 3,
    recruitment_state: str = "open",
    closed_reason: str | None = None,
) -> Team:
    closes_at = NOW + timedelta(days=7)
    team = Team(
        team_id=uuid4(),
        request_id=uuid4(),
        request_fingerprint="a" * 64,
        contest_id=contest.contest_id,
        leader_account_id=leader.account_id,
        name="테스트 팀",
        introduction="테스트 팀의 소개입니다.",
        target_capacity=capacity,
        recruitment_state=recruitment_state,
        closed_reason=closed_reason,
        recruitment_closes_at=closes_at,
        deadline_source_date=closes_at.date(),
        deadline_source_time=None,
        deadline_source_timezone=None,
        deadline_effective_timezone="Asia/Seoul",
        deadline_time_assumed=True,
        deadline_timezone_assumed=True,
    )
    session.add(team)
    await session.flush()
    session.add(
        TeamMembership(
            team_id=team.team_id,
            contest_id=contest.contest_id,
            account_id=leader.account_id,
            source_application_id=None,
            joined_at=NOW,
        )
    )
    if capacity > 1:
        session.add(TeamRecruitmentRole(team_id=team.team_id, role_code="development"))
    await session.flush()
    return team


async def seed_application(
    session: AsyncSession,
    team: Team,
    applicant: Account,
    *,
    status: str = "submitted",
) -> Application:
    application = Application(
        application_id=uuid4(),
        request_id=uuid4(),
        request_fingerprint="b" * 64,
        team_id=team.team_id,
        contest_id=team.contest_id,
        applicant_account_id=applicant.account_id,
        applied_role_code="development",
        status=status,
        submitted_at=NOW,
        status_changed_at=NOW,
    )
    session.add(application)
    await session.flush()
    return application


async def seed_membership(
    session: AsyncSession,
    team: Team,
    account: Account,
    *,
    joined_at: datetime = NOW,
    ended_at: datetime | None = None,
    application: Application | None = None,
) -> TeamMembership:
    if application is None:
        application = await seed_application(
            session,
            team,
            account,
            status="selected" if ended_at is None else "canceled",
        )
    membership = TeamMembership(
        team_membership_id=uuid4(),
        team_id=team.team_id,
        contest_id=team.contest_id,
        account_id=account.account_id,
        source_application_id=application.application_id,
        joined_at=joined_at,
        ended_at=ended_at,
        end_reason="application_canceled" if ended_at is not None else None,
    )
    session.add(membership)
    await session.flush()
    return membership


async def prepare_team(database: Database) -> tuple[UUID, UUID]:
    async with database.session() as session:
        leader = await seed_account(session)
        contest = await seed_contest(session)
        team = await seed_team(session, contest, leader)
        await session.commit()
        return team.team_id, leader.account_id
