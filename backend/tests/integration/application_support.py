"""지원 API 검사에 사용할 실제 PostgreSQL 행과 인증된 HTTP 요청을 준비한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import Settings
from app.core.db.base import Base
from app.core.db.session import Database
from app.core.http.handlers import register_error_handlers
from app.dependencies.auth import SESSION_COOKIE_NAME
from app.dependencies.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.models.applications import Application, ApplicationEvent
from app.models.auth import Account, AuthSession
from app.models.contests import Contest
from app.models.notifications import Notification
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole
from app.routers.applications import router
from app.security.csrf import issue_csrf_token
from app.services.sessions import IssuedSession, issue_session

ORIGIN = "https://api.example.test"
SIGNING_KEY = "application-tests-only-signing-key-32-bytes"


@dataclass(frozen=True)
class ApplicationData:
    database: Database
    applicant_id: UUID
    leader_id: UUID
    stranger_id: UUID
    contest_id: UUID
    team_id: UUID
    other_team_id: UUID
    application_id: UUID
    sessions: dict[UUID, IssuedSession]


def make_team(contest_id: UUID, leader_id: UUID, now: datetime) -> Team:
    return Team(
        team_id=uuid4(),
        request_id=uuid4(),
        request_fingerprint="a" * 64,
        contest_id=contest_id,
        leader_account_id=leader_id,
        name="지원 검사 팀",
        introduction="지원 흐름을 검사하는 팀입니다.",
        target_capacity=3,
        recruitment_state="open",
        closed_reason=None,
        recruitment_closes_at=now + timedelta(days=3),
        deadline_source_date=(now + timedelta(days=3)).date(),
        deadline_source_time=None,
        deadline_source_timezone=None,
        deadline_effective_timezone="Asia/Seoul",
        deadline_time_assumed=True,
        deadline_timezone_assumed=True,
    )


def make_application(
    team_id: UUID, contest_id: UUID, account_id: UUID, now: datetime
) -> Application:
    return Application(
        application_id=uuid4(),
        request_id=uuid4(),
        request_fingerprint="b" * 64,
        team_id=team_id,
        contest_id=contest_id,
        applicant_account_id=account_id,
        applied_role_code="development",
        message="함께 참여하겠습니다.",
        status="submitted",
        submitted_at=now,
        status_changed_at=now,
        version=1,
    )


@pytest_asyncio.fixture
async def application_data(database_url: str) -> AsyncIterator[ApplicationData]:
    schema = f"application_api_{uuid4().hex}"
    engine = create_async_engine(
        database_url,
        execution_options={"schema_translate_map": {None: schema}},
        connect_args={"server_settings": {"application_name": schema}},
    )
    database = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    tables = [
        cast(Table, model.__table__)
        for model in (
            Account,
            AuthSession,
            Contest,
            Team,
            TeamRecruitmentRole,
            Application,
            ApplicationEvent,
            TeamMembership,
            Notification,
        )
    ]
    try:
        async with engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(sync, tables=tables)
            )
        async with database.session() as session:
            accounts = [
                Account(
                    account_id=uuid4(),
                    login_id_normalized=name,
                    password_hash="test-only",
                )
                for name in ("applicant", "leader", "stranger")
            ]
            session.add_all(accounts)
            now = datetime.now(UTC) - timedelta(minutes=5)
            contest = Contest(
                contest_id=uuid4(),
                title="지원 검사 공모전",
                organizer_name="검사 주최자",
                official_url="https://example.test/contest",
                eligibility_text="원문 참고",
                member_limit_kind="range",
                min_members=1,
                max_members=5,
                verified_at=now,
                registration_opens_at=now - timedelta(days=1),
                registration_closes_at=now + timedelta(days=5),
                open_source_date=now.date(),
                open_source_time=None,
                open_source_timezone=None,
                open_effective_timezone="Asia/Seoul",
                open_timezone_assumed=True,
                close_source_date=(now + timedelta(days=5)).date(),
                close_source_time=None,
                close_source_timezone=None,
                close_effective_timezone="Asia/Seoul",
                close_time_assumed=True,
                close_timezone_assumed=True,
            )
            session.add(contest)
            await session.flush()
            applicant, leader, stranger = accounts
            first_team = make_team(contest.contest_id, leader.account_id, now)
            second_team = make_team(contest.contest_id, stranger.account_id, now)
            session.add_all([first_team, second_team])
            await session.flush()
            application = make_application(
                first_team.team_id, contest.contest_id, applicant.account_id, now
            )
            session.add(application)
            await session.flush()
            session.add(
                ApplicationEvent(
                    application_id=application.application_id,
                    team_id=first_team.team_id,
                    contest_id=contest.contest_id,
                    applicant_account_id=applicant.account_id,
                    application_version=1,
                    from_status=None,
                    to_status="submitted",
                    actor_account_id=applicant.account_id,
                    reason_code="submitted",
                    occurred_at=now,
                )
            )
            issued = {
                account.account_id: await issue_session(session, account.account_id)
                for account in accounts
            }
            await session.commit()
            data = ApplicationData(
                database,
                applicant.account_id,
                leader.account_id,
                stranger.account_id,
                contest.contest_id,
                first_team.team_id,
                second_team.team_id,
                application.application_id,
                issued,
            )
        yield data
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


@asynccontextmanager
async def application_client(
    data: ApplicationData, account_id: UUID | None
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.state.database = data.database
    app.state.settings = Settings(
        csrf_signing_key=SecretStr(SIGNING_KEY),
        auth_allowed_origins=(ORIGIN,),
        _env_file=None,
    )
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url=ORIGIN
    ) as client:
        if account_id is not None:
            issued = data.sessions[account_id]
            client.cookies.set(SESSION_COOKIE_NAME, issued.token)
            token = issue_csrf_token(SIGNING_KEY, issued.session.token_hash)
            client.cookies.set(CSRF_COOKIE_NAME, token)
            client.headers[CSRF_HEADER_NAME] = token
            client.headers["Origin"] = ORIGIN
        yield client
