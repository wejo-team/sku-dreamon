"""격리 PostgreSQL에서 시드 재구성의 상태·보존·롤백 경계를 검증한다."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.agents.types import AgentContext
from app.core.db.base import Base
from app.core.db.session import Database
from app.core.demo_data import DEV_ACCOUNT_IDS, DEV_TEAM_IDS
from app.models.academic_units import AcademicUnit
from app.models.ai_chat import AiConversation, AiMessage
from app.models.ai_runs import AiRun
from app.models.applications import Application, ApplicationEvent
from app.models.auth import Account, AuthSession
from app.models.contests import Contest, ContestAudience, ContestField
from app.models.courses import Course, ProfileCourse
from app.models.notifications import Notification
from app.models.profiles import (
    PortfolioLink,
    Profile,
    ProfileDesiredRole,
    ProfileInterest,
    ProfileSkill,
)
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole
from app.repositories.ai_runs import can_recommend_team
from app.rules.catalogs import RoleCode
from app.schemas.application_create import ApplicationCreate
from app.schemas.teams import TeamSearch
from app.services.ai_sources import SourceReader
from app.services.application_create import submit_application
from app.services.sessions import SessionPrincipal, issue_session
from app.services.teams import get_team_detail, list_teams
from scripts.dev_dataset import DatasetPlan
from scripts.dev_dataset_report import contest_fingerprint, dataset_report
from scripts.seed_dev_data import (
    clear_seed_teams,
    counts,
    load_plan,
    seed_teams,
    validate_seed,
)
from tests.integration.application_support import make_team

pytestmark = [pytest.mark.integration, pytest.mark.database]
TABLES = [
    Base.metadata.tables[model.__tablename__]
    for model in (
        Account,
        AuthSession,
        AcademicUnit,
        Profile,
        ProfileInterest,
        ProfileDesiredRole,
        ProfileSkill,
        Course,
        ProfileCourse,
        PortfolioLink,
        Contest,
        ContestAudience,
        ContestField,
        Team,
        TeamRecruitmentRole,
        Application,
        ApplicationEvent,
        TeamMembership,
        Notification,
        AiRun,
        AiConversation,
        AiMessage,
    )
]


@dataclass(frozen=True)
class SeedData:
    database: Database
    plan: DatasetPlan
    ordinary_account_id: UUID
    ordinary_team_id: UUID


async def stored_rows(
    session: AsyncSession, tables: Sequence[Table] = TABLES
) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for table in tables:
        rows = await session.execute(select(table).order_by(*table.primary_key))
        result[table.name] = [dict(row) for row in rows.mappings()]
    return result


@pytest.fixture
async def seed_data(database_url: str) -> AsyncIterator[SeedData]:
    schema = f"dev_dataset_{uuid4().hex}"
    engine = create_async_engine(
        database_url,
        execution_options={"schema_translate_map": {None: schema}},
        # validate_seed의 원문 SQL도 이 테스트에서 만든 테이블만 읽는다.
        connect_args={"server_settings": {"search_path": schema}},
    )
    database = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    try:
        async with engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(sync, tables=TABLES)
            )
        now = datetime.now(UTC).replace(microsecond=0)
        ordinary_id = uuid4()
        # 비밀번호 검증을 다루지 않으므로 해시 생성 없이 최소 참조 행을 준비한다.
        account_ids = (*DEV_ACCOUNT_IDS[:112], DEV_ACCOUNT_IDS[298], ordinary_id)
        async with database.session() as session:
            session.add_all(
                Account(
                    account_id=account_id,
                    login_id_normalized=(
                        f"devuser{DEV_ACCOUNT_IDS.index(account_id) + 1:03d}"
                        if account_id in DEV_ACCOUNT_IDS
                        else "ordinaryuser"
                    ),
                    password_hash="test-only",
                )
                for account_id in account_ids
            )
            contests = [
                Contest(
                    contest_id=uuid4(),
                    title=f"분산 검사 공고 {index + 1}",
                    organizer_name="검사 주최자",
                    official_url=f"https://example.test/contest/{index}",
                    eligibility_text="공식 원문 참고",
                    description="재구성 중 보존해야 하는 공고 원문",
                    member_limit_kind="range",
                    min_members=2,
                    max_members=5 if index < 3 else 2,
                    registration_opens_at=now - timedelta(days=1),
                    registration_closes_at=now + timedelta(days=40 + index),
                    open_source_date=(now - timedelta(days=1)).date(),
                    open_source_time=None,
                    open_source_timezone=None,
                    open_effective_timezone="Asia/Seoul",
                    open_timezone_assumed=True,
                    close_source_date=(now + timedelta(days=40 + index)).date(),
                    close_source_time=None,
                    close_source_timezone=None,
                    close_effective_timezone="Asia/Seoul",
                    close_time_assumed=True,
                    close_timezone_assumed=True,
                    created_at=now - timedelta(days=index),
                    updated_at=now,
                )
                for index in range(4)
            ]
            session.add_all(contests)
            await session.flush()
            session.add_all(
                Profile(
                    profile_id=account_id,
                    real_name=f"가상 사용자 {index}",
                    is_public=True,
                    introduction="사용자가 편집한 프로필은 보존합니다.",
                )
                for index, account_id in enumerate(account_ids)
            )
            await session.flush()
            course = Course(code="TEST101", name="편집한 수강 과목")
            session.add(course)
            await session.flush()
            session.add(
                ProfileCourse(account_id=DEV_ACCOUNT_IDS[0], course_id=course.course_id)
            )
            for account_id in account_ids:
                session.add(
                    ProfileInterest(account_id=account_id, field_code="it_technology")
                )
                session.add(
                    ProfileDesiredRole(account_id=account_id, role_code="development")
                )
            for contest, field in zip(
                contests,
                ("it_technology", "design", "environment", "public"),
                strict=True,
            ):
                session.add(
                    ContestField(contest_id=contest.contest_id, field_code=field)
                )
                session.add(
                    ContestAudience(
                        contest_id=contest.contest_id, audience_code="student"
                    )
                )
            ordinary_team = make_team(contests[-1].contest_id, ordinary_id, now)
            ordinary_team.target_capacity = 2
            session.add(ordinary_team)
            await session.flush()
            session.add(
                TeamMembership(
                    team_id=ordinary_team.team_id,
                    contest_id=ordinary_team.contest_id,
                    account_id=ordinary_id,
                    joined_at=now,
                )
            )
            session.add(
                TeamRecruitmentRole(
                    team_id=ordinary_team.team_id, role_code="development"
                )
            )
            await session.flush()
            plan = await load_plan(session, now)
            assert len(plan.contests) == 3
            # 실제 공고 선정은 사용하되 서비스 경계 검사는 공고당 한 쌍이면 충분하다.
            plan = replace(plan, assignments=plan.contests)
            await session.commit()
            data = SeedData(database, plan, ordinary_id, ordinary_team.team_id)
        yield data
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


async def test_seed_lifecycle_rebuild_and_idempotency_preserve_unrelated_data(
    seed_data: SeedData,
) -> None:
    async with seed_data.database.session() as session:
        originals = await stored_rows(session)
        assert len(originals["courses"]) == len(originals["profile_courses"]) == 1
        original_catalog = await contest_fingerprint(session)
        assert await seed_teams(session, seed_data.plan) == 6
        await validate_seed(session)
        development = await list_teams(
            session,
            TeamSearch.model_validate({"q": "개발", "recruitingOnly": True}),
        )
        assert development.data
        assert all("development" in item.role_codes for item in development.data)
        first_counts = await counts(session)
        assert set(await session.scalars(select(Application.status).distinct())) == {
            "submitted",
            "reviewing",
            "selected",
            "rejected",
            "canceled",
            "discarded",
        }
        assert set(await session.scalars(select(Team.closed_reason).distinct())) == {
            None,
            "capacity_reached",
            "leader_closed",
        }
        assert await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.read_at.is_(None))
        )
        assert await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.read_at.is_not(None))
        )
        for index in (1, 3, 5):
            team = await get_team_detail(session, DEV_TEAM_IDS[index])
            assert team.is_recruiting
            assert int(team.capacity) > team.member_count
            assert await can_recommend_team(
                session, team.id, team.contest_id, DEV_ACCOUNT_IDS[298]
            )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Application)
                .where(Application.applicant_account_id == DEV_ACCOUNT_IDS[298])
            )
            == 0
        )
        assert await seed_teams(session, seed_data.plan) == 0
        assert await counts(session) == first_counts
        assert await clear_seed_teams(session) == 6
        await session.commit()
        assert await stored_rows(session) == originals
        assert await seed_teams(session, seed_data.plan) == 6
        await validate_seed(session)
        assert await counts(session) == first_counts
        assert await contest_fingerprint(session) == original_catalog
        assert await session.get(Team, seed_data.ordinary_team_id) is not None


async def test_outer_rollback_restores_deleted_and_regenerated_graph(
    seed_data: SeedData,
) -> None:
    async with seed_data.database.session() as session:
        await seed_teams(session, seed_data.plan)
        original = await stored_rows(session)
    async with seed_data.database.engine.connect() as connection:
        async with connection.begin() as transaction:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                assert await clear_seed_teams(session) == 6
                await session.commit()
                assert await seed_teams(session, seed_data.plan) == 6
                await validate_seed(session)
                replacement = await stored_rows(session)
                assert replacement["applications"] != original["applications"]
                await session.commit()
            await transaction.rollback()
    async with seed_data.database.session() as session:
        # 총량뿐 아니라 원래 지원·발생 건 UUID와 모든 행 값이 복원되어야 한다.
        assert await stored_rows(session) == original


async def test_role_report_matches_authenticated_ai_source_search(
    seed_data: SeedData,
) -> None:
    async with seed_data.database.session() as session:
        await seed_teams(session, seed_data.plan)
        issued = await issue_session(session, DEV_ACCOUNT_IDS[298])
        await session.commit()
        report = await dataset_report(session, datetime.now(UTC))
    source = SourceReader(
        seed_data.database,
        AgentContext(
            principal=SessionPrincipal(
                auth_session_id=issued.session.auth_session_id,
                account_id=DEV_ACCOUNT_IDS[298],
                token_hash=issued.session.token_hash,
                expires_at=issued.session.expires_at,
            ),
            purpose="chat",
        ),
    )
    found = await source.search("team", 1, role_code=RoleCode.DEVELOPMENT)
    team_ids = found.ids
    assert team_ids
    resources = [await source.get("team", team_id) for team_id in team_ids]
    assert all("development" in item.role_codes for item in resources)
    role_checks = report["roleFirstPages"]
    assert isinstance(role_checks, dict)
    development = role_checks["development"]
    assert development["teamIds"] == [str(team_id) for team_id in team_ids]
    assert development["candidateCount"] == len(team_ids)


async def test_rebuild_rejects_real_account_activity_before_deleting_any_row(
    seed_data: SeedData,
) -> None:
    async with seed_data.database.session() as session:
        await seed_teams(session, seed_data.plan)
        body = ApplicationCreate.model_validate(
            {
                "requestId": str(uuid4()),
                "roleCode": "development",
                "message": "직접 지원",
            }
        )
        await submit_application(
            session, seed_data.ordinary_account_id, DEV_TEAM_IDS[1], body
        )
        before = await stored_rows(session)
        with pytest.raises(ValueError, match="일반 계정"):
            await clear_seed_teams(session)
        assert await stored_rows(session) == before


async def add_run(
    session: AsyncSession,
    account_id: UUID,
    *,
    team_id: UUID | None,
    expired: bool,
) -> UUID:
    issued = await issue_session(session, account_id)
    now = datetime.now(UTC)
    created = now - timedelta(days=2)
    run_id = uuid4()
    conversation_id, message_id = (
        (uuid4(), uuid4()) if team_id is None else (None, None)
    )
    session.add(
        AiRun(
            ai_run_id=run_id,
            account_id=account_id,
            auth_session_id=issued.session.auth_session_id,
            purpose="chat" if team_id is None else "applicant_recommendation",
            scope_key=str(conversation_id or team_id),
            conversation_id=conversation_id,
            client_message_id=message_id,
            team_id=team_id,
            application_id=None,
            request_fingerprint="a" * 64,
            attempt=1,
            status="canceled",
            created_at=created,
            updated_at=created,
            deadline_at=created + timedelta(minutes=1),
            expires_at=now + timedelta(hours=-1 if expired else 1),
        )
    )
    if conversation_id is not None:
        session.add(
            AiConversation(
                ai_conversation_id=conversation_id,
                account_id=account_id,
                created_at=created,
                updated_at=created,
            )
        )
        await session.flush()
        session.add(
            AiMessage(
                ai_conversation_id=conversation_id,
                client_message_id=message_id,
                request_id=run_id,
                role="user",
                content="팀 재구성 후에도 보존할 일반 대화",
                attempt=1,
                created_at=created,
            )
        )
    await session.commit()
    return run_id


async def test_rebuild_removes_only_expired_seed_review_runs_and_preserves_chat(
    seed_data: SeedData,
) -> None:
    async with seed_data.database.session() as session:
        await seed_teams(session, seed_data.plan)
        expired_id = await add_run(
            session, DEV_ACCOUNT_IDS[0], team_id=DEV_TEAM_IDS[0], expired=True
        )
        chat_id = await add_run(
            session, seed_data.ordinary_account_id, team_id=None, expired=True
        )
        chat_tables = [
            Base.metadata.tables[name]
            for name in ("ai_conversations", "ai_messages", "auth_sessions")
        ]
        before = await stored_rows(session, chat_tables)
        assert await clear_seed_teams(session) == 6
        await session.commit()
        assert await session.get(AiRun, expired_id) is None
        assert await session.get(AiRun, chat_id) is not None
        assert await stored_rows(session, chat_tables) == before


@pytest.mark.parametrize("seed_owner,expired", [(True, False), (False, True)])
async def test_rebuild_preserves_unexpired_or_real_account_review_runs(
    seed_data: SeedData, seed_owner: bool, expired: bool
) -> None:
    async with seed_data.database.session() as session:
        await seed_teams(session, seed_data.plan)
        await add_run(
            session,
            DEV_ACCOUNT_IDS[0] if seed_owner else seed_data.ordinary_account_id,
            team_id=DEV_TEAM_IDS[0],
            expired=expired,
        )
        before = await stored_rows(session)
        with pytest.raises(ValueError, match="메타데이터"):
            await clear_seed_teams(session)
        assert await stored_rows(session) == before
