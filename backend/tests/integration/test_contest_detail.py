"""공개 공고 상세의 원문·경계·전체 팀 수와 단일 조회 시점을 검증한다."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table, update
from sqlalchemy.engine import Result
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlalchemy.sql.base import Executable

from app.core import demo_data as manifest
from app.core.db.base import Base
from app.core.db.session import Database
from app.core.http.dependencies import get_session
from app.core.http.handlers import register_error_handlers
from app.models.auth import Account
from app.models.contests import Contest, ContestAudience, ContestField
from app.models.teams import Team
from app.routers.contests import router
from app.services import contests as queries

pytestmark = [pytest.mark.integration, pytest.mark.database]
START = datetime(2026, 10, 24, 1, tzinfo=UTC)
END = datetime(2026, 10, 24, 15, tzinfo=UTC)
CONTEST_ID, OWNER_ID = UUID(int=1), UUID(int=2)


@dataclass
class ContestApi:
    database: Database
    client: AsyncClient


def make_contest(contest_id: UUID = CONTEST_ID) -> Contest:
    return Contest(
        contest_id=contest_id,
        title="원문 제목",
        organizer_name="공개 주최자",
        official_url="https://example.test/official",
        eligibility_text="원문 참가 조건",
        description="확인된 설명",
        submission_details="제출물 원문",
        awards=None,
        contact_info="문의처 원문",
        poster_url=None,
        member_limit_kind="range",
        min_members=1,
        max_members=9223372036854775807,
        verified_at=START - timedelta(days=1),
        registration_opens_at=START,
        registration_closes_at=END,
        open_source_date=date(2026, 10, 24),
        open_source_time=time(10),
        open_source_timezone="Asia/Seoul",
        open_effective_timezone="Asia/Seoul",
        open_timezone_assumed=False,
        close_source_date=date(2026, 10, 24),
        close_source_time=None,
        close_source_timezone=None,
        close_effective_timezone="Asia/Seoul",
        close_time_assumed=True,
        close_timezone_assumed=True,
    )


def make_team(contest_id: UUID, *, closed: bool = False) -> Team:
    return Team(
        request_id=uuid4(),
        request_fingerprint="a" * 64,
        contest_id=contest_id,
        leader_account_id=OWNER_ID,
        name="공개 팀",
        introduction="공개 팀 소개입니다.",
        target_capacity=3,
        recruitment_state="closed" if closed else "open",
        closed_reason="leader_closed" if closed else None,
        recruitment_closes_at=END,
        deadline_source_date=date(2026, 10, 24),
        deadline_source_time=None,
        deadline_source_timezone=None,
        deadline_effective_timezone="Asia/Seoul",
        deadline_time_assumed=True,
        deadline_timezone_assumed=True,
    )


@pytest_asyncio.fixture
async def api(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[ContestApi]:
    schema = f"contest_detail_test_{uuid4().hex}"
    engine = create_async_engine(
        database_url, execution_options={"schema_translate_map": {None: schema}}
    )
    database = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    tables = [
        cast(Table, model.__table__)
        for model in (Account, Contest, ContestAudience, ContestField, Team)
    ]
    try:
        async with engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=tables)
            )
        async with database.session() as session:
            session.add(
                Account(
                    account_id=OWNER_ID,
                    login_id_normalized="privateowner",
                    password_hash="private-password",
                )
            )
            session.add_all([make_contest(), make_contest(UUID(int=3))])
            await session.flush()
            session.add_all(
                [
                    ContestAudience(contest_id=CONTEST_ID, audience_code="student"),
                    ContestAudience(contest_id=CONTEST_ID, audience_code="general"),
                    ContestField(contest_id=CONTEST_ID, field_code="design"),
                    ContestField(contest_id=CONTEST_ID, field_code="it_technology"),
                    make_team(CONTEST_ID),
                    make_team(CONTEST_ID, closed=True),
                    make_team(UUID(int=3)),
                ]
            )
            await session.commit()
        app = FastAPI()
        register_error_handlers(app)
        app.include_router(router, prefix="/api/v1")

        async def request_session() -> AsyncIterator[AsyncSession]:
            async with database.session() as session:
                session.info["contest_detail_request"] = True
                yield session

        app.dependency_overrides[get_session] = request_session
        monkeypatch.setattr(queries, "_utcnow", lambda: START)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="https://example.test",
        ) as client:
            yield ContestApi(database, client)
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


async def test_anonymous_detail_returns_current_public_source_and_all_teams(
    api: ContestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(manifest, "CONTEST_IDS", frozenset({CONTEST_ID}))
    response = await api.client.get(f"/api/v1/contests/{CONTEST_ID}")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["title"] == "원문 제목" and data["teamCount"] == 2 and data["isDemo"]
    assert data["fieldCodes"] == ["it_technology", "design"]
    assert set(data["audienceCodes"]) == {"student", "general"}
    assert data["eligibilityText"] == "원문 참가 조건"
    assert data["sourceUrl"] == "https://example.test/official"
    assert data["officialUrl"] == data["sourceUrl"]
    assert data["verifiedAt"] == "2026-10-23T01:00:00Z"
    assert data["timing"]["openTimeDefaulted"] is False
    assert data["deliverables"] == "제출물 원문" and data["contact"] == "문의처 원문"
    assert data["awards"] is None and data["posterUrl"] is None
    assert data["capacity"] == {
        "kind": "range",
        "minimumMembers": "1",
        "maximumMembers": "9223372036854775807",
    }
    assert data["timing"]["startsAt"] == data["startsAt"] == "2026-10-24T01:00:00Z"
    assert data["timing"]["endsAt"] == data["endsAt"] == "2026-10-24T15:00:00Z"
    assert data["timing"]["closing"] == {
        "sourceDate": "2026-10-24",
        "sourceTime": None,
        "sourceTimeZone": None,
        "effectiveTimeZone": "Asia/Seoul",
        "timeDefaulted": True,
        "timeZoneDefaulted": True,
    }
    assert set(data) == {
        "id",
        "title",
        "organizer",
        "fieldCodes",
        "posterUrl",
        "registrationStatus",
        "startsAt",
        "endsAt",
        "teamCount",
        "isDemo",
        "createdAt",
        "version",
        "description",
        "audienceCodes",
        "eligibilityText",
        "capacity",
        "timing",
        "deliverables",
        "awards",
        "contact",
        "verifiedAt",
        "sourceUrl",
        "officialUrl",
    }
    assert "private-" not in response.text and "privateowner" not in response.text


@pytest.mark.parametrize(
    "moment,status",
    [
        (START - timedelta(microseconds=1), "scheduled"),
        (START, "open"),
        (END - timedelta(microseconds=1), "open"),
        (END, "closed"),
    ],
)
async def test_all_registration_states_remain_public_at_exact_boundaries(
    api: ContestApi, monkeypatch: pytest.MonkeyPatch, moment: datetime, status: str
) -> None:
    monkeypatch.setattr(queries, "_utcnow", lambda: moment)
    response = await api.client.get(f"/api/v1/contests/{CONTEST_ID}")
    assert response.status_code == 200
    assert response.json()["data"]["registrationStatus"] == status


@pytest.mark.parametrize(
    "kind,minimum", [("unlimited", None), ("unlimited", 2), ("unknown", None)]
)
async def test_unknown_and_unlimited_capacity_keep_required_nulls(
    api: ContestApi, kind: str, minimum: int | None
) -> None:
    async with api.database.session() as session:
        await session.execute(
            update(Contest)
            .where(Contest.contest_id == CONTEST_ID)
            .values(member_limit_kind=kind, min_members=minimum, max_members=None)
        )
        await session.commit()
    response = await api.client.get(f"/api/v1/contests/{CONTEST_ID}")
    assert response.status_code == 200
    assert response.json()["data"]["capacity"] == {
        "kind": kind,
        "minimumMembers": None if minimum is None else str(minimum),
        "maximumMembers": None,
    }


async def test_original_times_and_missing_start_time_are_not_reinterpreted(
    api: ContestApi,
) -> None:
    async with api.database.session() as session:
        await session.execute(
            update(Contest)
            .where(Contest.contest_id == CONTEST_ID)
            .values(
                open_source_time=None,
                open_source_timezone=None,
                open_timezone_assumed=True,
                close_source_time=time(11),
                close_source_timezone="America/New_York",
                close_effective_timezone="America/New_York",
                close_time_assumed=False,
                close_timezone_assumed=False,
            )
        )
        await session.commit()
    response = await api.client.get(f"/api/v1/contests/{CONTEST_ID}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["timing"]["openSourceTime"] is None
    assert data["timing"]["openSourceTimeZone"] is None
    assert data["timing"]["openTimeZoneDefaulted"] is True
    assert data["startsAt"] == "2026-10-24T01:00:00Z"
    assert data["timing"]["closing"] == {
        "sourceDate": "2026-10-24",
        "sourceTime": "11:00:00",
        "sourceTimeZone": "America/New_York",
        "effectiveTimeZone": "America/New_York",
        "timeDefaulted": False,
        "timeZoneDefaulted": False,
    }


async def test_missing_and_invalid_ids_and_openapi_contract(api: ContestApi) -> None:
    missing = await api.client.get(f"/api/v1/contests/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CONTEST_NOT_FOUND"
    invalid = await api.client.get("/api/v1/contests/private-invalid-id")
    assert invalid.status_code == 422 and "private-invalid-id" not in invalid.text
    document = (await api.client.get("/openapi.json")).json()
    operation = document["paths"]["/api/v1/contests/{contestId}"]["get"]
    assert not operation.get("security")
    assert set(operation["responses"]) == {"200", "404", "422", "500", "503"}
    assert operation["parameters"][0]["name"] == "contestId"
    assert operation["parameters"][0]["schema"]["format"] == "uuid"
    assert "/api/v1/contests" in document["paths"]


async def test_source_and_team_count_share_one_snapshot(
    api: ContestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = AsyncSession.execute
    modified = False

    async def execute_then_change(
        self: AsyncSession, statement: Executable
    ) -> Result[tuple[object, ...]]:
        nonlocal modified
        result = await original(self, statement)
        if self.info.get("contest_detail_request") and not modified:
            modified = True
            async with api.database.session() as writer:
                await writer.execute(
                    update(Contest)
                    .where(Contest.contest_id == CONTEST_ID)
                    .values(title="수정된 제목")
                )
                writer.add(make_team(CONTEST_ID))
                await writer.commit()
        return result

    monkeypatch.setattr(AsyncSession, "execute", execute_then_change)
    first = (await api.client.get(f"/api/v1/contests/{CONTEST_ID}")).json()["data"]
    second = (await api.client.get(f"/api/v1/contests/{CONTEST_ID}")).json()["data"]
    assert (first["title"], first["teamCount"]) == ("원문 제목", 2)
    assert (second["title"], second["teamCount"]) == ("수정된 제목", 3)


async def test_existing_identity_map_does_not_reuse_old_public_fields(
    api: ContestApi,
) -> None:
    async with api.database.session() as session:
        loaded = await session.get(Contest, CONTEST_ID)
        assert loaded is not None
        async with api.database.session() as writer:
            await writer.execute(
                update(Contest)
                .where(Contest.contest_id == CONTEST_ID)
                .values(title="현재 제목")
            )
            await writer.commit()
        detail = await queries.get_contest_detail(session, CONTEST_ID, now=START)
        assert detail.title == "현재 제목"
        assert session.in_transaction()


@pytest.mark.parametrize(
    "column,response_field",
    [("official_url", "sourceUrl"), ("poster_url", "posterUrl")],
)
async def test_long_http_urls_keep_the_stored_value_without_an_implicit_limit(
    api: ContestApi, column: str, response_field: str
) -> None:
    prefix = "https://example.test/resource?source="
    long_url = prefix + "x" * (2129 - len(prefix))
    async with api.database.session() as session:
        await session.execute(
            update(Contest)
            .where(Contest.contest_id == CONTEST_ID)
            .values({column: long_url})
        )
        await session.commit()
    response = await api.client.get(f"/api/v1/contests/{CONTEST_ID}")
    assert response.status_code == 200
    assert response.json()["data"][response_field] == long_url
    document = (await api.client.get("/openapi.json")).json()
    field = document["components"]["schemas"]["ContestDetail"]["properties"][
        response_field
    ]
    assert "maxLength" not in str(field)


async def test_collected_source_keeps_unknown_verification_and_opening(
    api: ContestApi,
) -> None:
    async with api.database.session() as session:
        await session.execute(
            update(Contest)
            .where(Contest.contest_id == CONTEST_ID)
            .values(
                official_url=None,
                source_url="https://example.test/collected",
                verified_at=None,
                source_metadata={
                    "externalId": "collected-1",
                    "raw": {"internalNote": "private-source-metadata"},
                },
                open_source_time=None,
                registration_opens_at=datetime(2026, 10, 23, 15, tzinfo=UTC),
            )
        )
        await session.commit()
    response = await api.client.get(f"/api/v1/contests/{CONTEST_ID}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sourceUrl"] == "https://example.test/collected"
    assert data["officialUrl"] is None and data["verifiedAt"] is None
    assert data["timing"]["openTimeDefaulted"] is True
    assert data["timing"]["openSourceTime"] is None
    assert "sourceMetadata" not in data
    assert "private-source-metadata" not in response.text
    async with api.database.session() as session:
        stored = await session.get(Contest, CONTEST_ID)
        assert stored is not None
        assert stored.source_metadata["raw"] == {
            "internalNote": "private-source-metadata"
        }


async def test_official_link_takes_precedence_without_claiming_verification(
    api: ContestApi,
) -> None:
    async with api.database.session() as session:
        await session.execute(
            update(Contest)
            .where(Contest.contest_id == CONTEST_ID)
            .values(source_url="https://example.test/collected", verified_at=None)
        )
        await session.commit()
    response = await api.client.get(f"/api/v1/contests/{CONTEST_ID}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sourceUrl"] == data["officialUrl"] == "https://example.test/official"
    assert data["verifiedAt"] is None


async def test_contest_cannot_lose_both_source_links(api: ContestApi) -> None:
    async with api.database.session() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                update(Contest)
                .where(Contest.contest_id == CONTEST_ID)
                .values(official_url=None, source_url=None)
            )
        await session.rollback()
