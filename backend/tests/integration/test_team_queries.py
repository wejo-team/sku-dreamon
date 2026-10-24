"""공개 팀 HTTP 조회의 실제 집계·검색·페이지·한 시점 읽기를 검증한다."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table, update
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlalchemy.sql.base import Executable

from app.core import demo_data as manifest
from app.core.db.base import Base
from app.core.db.session import Database
from app.core.http.dependencies import get_session
from app.core.http.handlers import register_error_handlers
from app.models.applications import Application
from app.models.auth import Account
from app.models.contests import Contest, ContestField
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole
from app.routers.teams import router
from app.services import teams as queries

pytestmark = [pytest.mark.integration, pytest.mark.database]
NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


@dataclass
class TeamApi:
    database: Database
    client: AsyncClient


def new_contest(index: int) -> Contest:
    return Contest(
        contest_id=UUID(int=index),
        title=f"공모전 제목 {index}",
        organizer_name="공개 기관",
        official_url="https://example.org/contest",
        eligibility_text="원문 확인",
        member_limit_kind="range",
        min_members=1,
        max_members=10,
        verified_at=NOW,
        version=1,
        registration_opens_at=NOW + timedelta(days=1 if index == 3 else -1),
        registration_closes_at=NOW + timedelta(days=0 if index == 2 else 10),
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
        created_at=NOW - timedelta(days=2),
    )


def new_team(index: int, contest_id: UUID, leader_id: UUID) -> Team:
    return Team(
        team_id=UUID(int=index),
        request_id=uuid4(),
        request_fingerprint="a" * 64,
        contest_id=contest_id,
        leader_account_id=leader_id,
        name="Alpha 100% 연구" if index == 100 else f"팀 {index}",
        introduction="공개 팀의 소개입니다.",
        target_capacity=1 if index == 102 else 3,
        recruitment_state="closed" if index == 101 else "open",
        closed_reason="leader_closed" if index == 101 else None,
        recruitment_closes_at=NOW + timedelta(days=0 if index == 105 else 5),
        deadline_source_date=date(2026, 10, 29),
        deadline_source_time=None,
        deadline_source_timezone=None,
        deadline_effective_timezone="Asia/Seoul",
        deadline_time_assumed=True,
        deadline_timezone_assumed=True,
        version=1,
        created_at=NOW - timedelta(days=1),
    )


@pytest_asyncio.fixture
async def api(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[TeamApi]:
    schema = f"team_query_test_{uuid4().hex}"
    engine = create_async_engine(
        database_url, execution_options={"schema_translate_map": {None: schema}}
    )
    database = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    tables = [
        cast(Table, model.__table__)
        for model in (
            Account,
            Contest,
            ContestField,
            Team,
            TeamRecruitmentRole,
            Application,
            TeamMembership,
        )
    ]
    try:
        async with engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=tables)
            )
        async with database.session() as session:
            contests = [new_contest(index) for index in range(1, 5)]
            accounts = [
                Account(
                    account_id=UUID(int=1000 + index),
                    login_id_normalized=f"person{index}",
                    password_hash="private-password-hash",
                )
                for index in range(8)
            ]
            session.add_all([*contests, *accounts])
            await session.flush()
            teams = [
                new_team(
                    100 + index,
                    UUID(int=2 if index == 3 else 3 if index == 4 else 1),
                    accounts[index].account_id,
                )
                for index in range(6)
            ]
            session.add_all(teams)
            session.add_all(
                [
                    ContestField(contest_id=UUID(int=1), field_code=code)
                    for code in ("design", "it_technology")
                ]
            )
            await session.flush()
            session.add_all(
                [
                    TeamMembership(
                        team_id=team.team_id,
                        contest_id=team.contest_id,
                        account_id=team.leader_account_id,
                        joined_at=NOW - timedelta(days=1),
                    )
                    for team in teams
                ]
            )
            session.add_all(
                [
                    TeamRecruitmentRole(team_id=UUID(int=100), role_code=code)
                    for code in ("planning", "development")
                ]
            )
            for index, status in ((6, "selected"), (7, "canceled")):
                application = Application(
                    application_id=uuid4(),
                    request_id=uuid4(),
                    request_fingerprint="b" * 64,
                    team_id=UUID(int=100),
                    contest_id=UUID(int=1),
                    applicant_account_id=accounts[index].account_id,
                    applied_role_code="development",
                    message="private application message",
                    status=status,
                    submitted_at=NOW - timedelta(days=1),
                    status_changed_at=NOW,
                )
                session.add(application)
                await session.flush()
                session.add(
                    TeamMembership(
                        team_id=UUID(int=100),
                        contest_id=UUID(int=1),
                        account_id=accounts[index].account_id,
                        source_application_id=application.application_id,
                        joined_at=NOW - timedelta(hours=1),
                        ended_at=NOW if status == "canceled" else None,
                        end_reason="application_canceled"
                        if status == "canceled"
                        else None,
                    )
                )
            await session.commit()
        app = FastAPI()
        app.state.database = database
        register_error_handlers(app)
        app.include_router(router, prefix="/api/v1")

        async def request_session() -> AsyncIterator[AsyncSession]:
            async with database.session() as session:
                session.info["public_team_request"] = True
                yield session

        app.dependency_overrides[get_session] = request_session
        monkeypatch.setattr(queries, "_utcnow", lambda: NOW)
        monkeypatch.setattr(manifest, "TEAM_IDS", frozenset({UUID(int=100)}))
        monkeypatch.setattr(manifest, "CONTEST_IDS", frozenset({UUID(int=1)}))
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            yield TeamApi(database, client)
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


async def test_anonymous_detail_uses_actual_counts_and_only_public_fields(
    api: TeamApi,
) -> None:
    response = await api.client.get(f"/api/v1/teams/{UUID(int=100)}")
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["memberCount"] == 2
    assert body["contest"]["teamCount"] == 4
    assert body["ownerAccountId"] == str(UUID(int=1000))
    assert body["isDemo"] and body["contest"]["isDemo"]
    assert body["fieldCodes"] == ["it_technology", "design"]
    assert body["roleCodes"] == ["planning", "development"]
    assert body["isRecruiting"] is True
    assert body["contest"]["registrationStatus"] == "open"
    assert body["capacity"] == "3" and body["version"] == "1"
    assert body["recruitmentEndsAt"].endswith("Z")
    assert body["contest"]["posterUrl"] is None
    assert "private" not in response.text
    assert (
        "members" not in body and "applications" not in body and "profile" not in body
    )
    assert body["recruitmentDeadline"]["sourceTime"] is None


async def test_lists_are_stable_clamped_and_keep_closed_scheduled_and_full_teams(
    api: TeamApi,
) -> None:
    response = await api.client.get("/api/v1/teams", params={"page": 99, "pageSize": 2})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pagination"] == {"page": 3, "pageSize": 2, "total": 6, "totalPages": 3}
    assert [item["id"] for item in body["data"]] == [
        str(UUID(int=101)),
        str(UUID(int=100)),
    ]
    full = await api.client.get("/api/v1/teams")
    assert len(full.json()["data"]) == 6
    assert [item["id"] for item in full.json()["data"] if item["isRecruiting"]] == [
        str(UUID(int=100))
    ]
    closed = await api.client.get(f"/api/v1/teams/{UUID(int=103)}")
    assert closed.status_code == 200 and closed.json()["data"]["isRecruiting"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"q": "  Alpha  "},
        {"q": "개발"},
        {"roleCode": "development"},
        {"recruitingOnly": "true"},
        {"q": "100%"},
    ],
)
async def test_team_search_filters_use_their_declared_meaning(
    api: TeamApi, params: dict[str, str]
) -> None:
    response = await api.client.get("/api/v1/teams", params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body["data"]] == [str(UUID(int=100))]
    assert body["pagination"]["total"] == 1


async def test_contest_scope_and_search_sources_are_distinct(api: TeamApi) -> None:
    prefix = f"/api/v1/contests/{UUID(int=1)}/teams"
    scoped = await api.client.get(prefix)
    assert scoped.status_code == 200 and scoped.json()["pagination"]["total"] == 4
    all_search = await api.client.get("/api/v1/teams", params={"q": "공모전 제목 1"})
    assert all_search.json()["pagination"]["total"] == 4
    scoped_search = await api.client.get(prefix, params={"q": "공모전 제목 1"})
    assert scoped_search.json()["data"] == []
    filtered = await api.client.get(
        "/api/v1/teams", params={"contestId": str(UUID(int=2))}
    )
    assert [item["id"] for item in filtered.json()["data"]] == [str(UUID(int=103))]
    assert (await api.client.get("/api/v1/teams", params={"q": "%"})).json()[
        "pagination"
    ]["total"] == 1
    assert (await api.client.get("/api/v1/teams", params={"q": "_"})).json()[
        "pagination"
    ]["total"] == 0


async def test_empty_existing_contest_is_distinct_from_missing_contest(
    api: TeamApi,
) -> None:
    empty = await api.client.get(
        f"/api/v1/contests/{UUID(int=4)}/teams", params={"page": 99}
    )
    assert empty.status_code == 200
    assert empty.json() == {
        "data": [],
        "pagination": {"page": 1, "pageSize": 20, "total": 0, "totalPages": 0},
    }
    for path in (f"/api/v1/contests/{uuid4()}/teams", f"/api/v1/teams/{uuid4()}"):
        assert (await api.client.get(path)).status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"page": "0"},
        {"page": "1.5"},
        {"page": "9007199254740992"},
        {"pageSize": "101"},
        {"roleCode": "invalid"},
        {"page_size": "3"},
        {"contestId": "invalid"},
        {"secret": "value"},
    ],
)
async def test_query_validation_rejects_invalid_or_undeclared_input(
    api: TeamApi, params: dict[str, str]
) -> None:
    response = await api.client.get("/api/v1/teams", params=params)
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"][0] == "query"


async def test_snapshot_keeps_count_and_rows_consistent_across_a_concurrent_commit(
    api: TeamApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = AsyncSession.execute
    modified = False

    async def execute_with_concurrent_change(
        self: AsyncSession, statement: Executable
    ) -> Result[tuple[object, ...]]:
        nonlocal modified
        result = await original(self, statement)
        if self.info.get("public_team_request") and not modified:
            modified = True
            async with api.database.session() as writer:
                await writer.execute(
                    update(Team)
                    .where(Team.team_id == UUID(int=100))
                    .values(
                        recruitment_state="closed",
                        closed_reason="leader_closed",
                        name="changed",
                    )
                )
                await writer.commit()
        return result

    monkeypatch.setattr(AsyncSession, "execute", execute_with_concurrent_change)
    response = await api.client.get("/api/v1/teams", params={"recruitingOnly": "true"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pagination"]["total"] == 1 and len(body["data"]) == 1
    assert body["data"][0]["name"] == "Alpha 100% 연구"
    assert body["data"][0]["isRecruiting"] is True
    after = await api.client.get("/api/v1/teams", params={"recruitingOnly": "true"})
    assert after.json()["pagination"]["total"] == 0 and after.json()["data"] == []


async def test_openapi_and_http_use_the_same_public_contract(api: TeamApi) -> None:
    schema = (await api.client.get("/openapi.json")).json()
    operation = schema["paths"]["/api/v1/teams"]["get"]
    assert {p["name"] for p in operation["parameters"]} == {
        "page",
        "pageSize",
        "q",
        "roleCode",
        "recruitingOnly",
        "contestId",
    }
    assert not operation.get("security")
    assert {"422", "500", "503"} <= set(operation["responses"])
    detail = schema["paths"]["/api/v1/teams/{teamId}"]["get"]
    assert "404" in detail["responses"]
    fields = schema["components"]["schemas"]["TeamDetail"]["properties"]
    assert "ownerAccountId" in fields and "contest" in fields
    assert "members" not in fields and "applications" not in fields


async def test_existing_identity_map_does_not_override_a_current_database_read(
    api: TeamApi,
) -> None:
    async with api.database.session() as reader:
        existing = await reader.get(Team, UUID(int=100))
        assert existing is not None
        async with api.database.session() as writer:
            await writer.execute(
                update(Team)
                .where(Team.team_id == existing.team_id)
                .values(name="현재 팀명", version=2)
            )
            await writer.commit()
        result = await queries.get_team_detail(reader, existing.team_id)
        assert result.name == "현재 팀명" and result.version == "2"


@pytest.mark.parametrize(
    "path", ["/api/v1/teams", f"/api/v1/contests/{UUID(int=1)}/teams"]
)
async def test_team_search_rejects_nul_before_database_lookup(
    api: TeamApi, path: str
) -> None:
    response = await api.client.get(path, params={"q": "검색\x00어"})
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["query", "q"]
