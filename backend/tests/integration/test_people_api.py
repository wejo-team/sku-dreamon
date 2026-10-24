"""PostgreSQL과 HTTP 경계에서 프로필 공개 범위·검색·페이지 계약을 검증한다."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import get_args
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Select, insert, select, update
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core import demo_data as manifest
from app.core.db.base import Base
from app.core.db.session import Database, create_database
from app.core.http.dependencies import get_session
from app.core.http.handlers import register_error_handlers
from app.dependencies.auth import SESSION_COOKIE_NAME, CurrentAccount
from app.models.academic_units import AcademicUnit
from app.models.auth import Account, AuthSession
from app.models.profiles import (
    PortfolioLink,
    Profile,
    ProfileDesiredRole,
    ProfileInterest,
    ProfileSkill,
)
from app.queries import profiles as queries
from app.routers.profiles import router
from app.schemas.profiles import PeopleQuery
from app.services import profiles as service
from app.services.sessions import issue_session

pytestmark = [pytest.mark.integration, pytest.mark.database]
ACCOUNT_ID = UUID(int=1)
PUBLIC_ID = UUID(int=2)
DEMO_ID = UUID(int=3)
metadata = Base.metadata
tables = [
    metadata.tables[model.__tablename__]
    for model in (
        Account,
        AuthSession,
        AcademicUnit,
        Profile,
        ProfileInterest,
        ProfileDesiredRole,
        ProfileSkill,
        PortfolioLink,
    )
]


@pytest.fixture
async def people_database(database_url: str) -> AsyncIterator[Database]:
    database = create_database(database_url)
    schema = f"people_test_{uuid4().hex}"
    try:
        async with database.engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            await connection.execution_options(schema_translate_map={None: schema})
            await connection.run_sync(lambda sync: metadata.create_all(sync, tables))
        database.engine.update_execution_options(schema_translate_map={None: schema})
        yield database
    finally:
        async with database.engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await database.engine.dispose()


async def add_profile(
    database: Database,
    account_id: UUID,
    *,
    public: bool = True,
    name: str = "예시 사용자",
    fields: tuple[str, ...] = ("it_technology",),
    roles: tuple[str, ...] = ("development",),
    skills: tuple[str, ...] = (),
    updated_at: datetime = datetime(2026, 10, 24, tzinfo=UTC),
) -> None:
    async with database.session() as session:
        await session.execute(
            insert(metadata.tables["accounts"]).values(
                account_id=account_id,
                login_id_normalized=f"person{account_id.int}",
                password_hash="test-hash",
            )
        )
        await session.execute(
            insert(metadata.tables["profiles"]).values(
                profile_id=account_id,
                real_name=name,
                is_public=public,
                updated_at=updated_at,
                introduction="협업을 희망합니다.",
            )
        )
        for table_name, code_column, values in (
            ("profile_interests", "field_code", fields),
            ("profile_desired_roles", "role_code", roles),
            ("profile_skills", "skill_code", skills),
        ):
            if values:
                await session.execute(
                    insert(metadata.tables[table_name]),
                    [
                        {"account_id": account_id, code_column: value}
                        for value in values
                    ],
                )
        await session.commit()


@pytest.fixture
async def people_client(
    people_database: Database, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")

    async def session_override() -> AsyncIterator[object]:
        async with people_database.session() as session:
            yield session

    async def account_override() -> UUID:
        return ACCOUNT_ID

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_args(CurrentAccount)[1].dependency] = account_override
    demo_accounts = frozenset({DEMO_ID})
    monkeypatch.setattr(manifest, "ACCOUNT_IDS", demo_accounts)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def test_public_listing_filters_private_profiles_and_clamps_pages(
    people_database: Database, people_client: AsyncClient
) -> None:
    await add_profile(people_database, ACCOUNT_ID, public=False, name="숨김")
    await add_profile(people_database, PUBLIC_ID, name="공개")
    await add_profile(people_database, DEMO_ID, name="시연")

    response = await people_client.get("/api/v1/people?page=999&pageSize=1")
    assert response.status_code == 200
    assert response.json()["pagination"] == {
        "page": 2,
        "pageSize": 1,
        "total": 2,
        "totalPages": 2,
    }
    assert response.json()["data"][0]["accountId"] == str(DEMO_ID)
    assert response.json()["data"][0]["isDemo"] is True
    first = await people_client.get("/api/v1/people?pageSize=1")
    assert first.json()["data"][0]["accountId"] == str(PUBLIC_ID)
    assert first.json()["data"][0]["isDemo"] is False


async def test_search_uses_labels_and_exact_filters_without_duplicate_people(
    people_database: Database, people_client: AsyncClient
) -> None:
    await add_profile(
        people_database,
        PUBLIC_ID,
        fields=("design", "it_technology"),
        roles=("planning", "development"),
        skills=("video_editing",),
    )
    await add_profile(people_database, DEMO_ID, fields=("design",), roles=("design",))
    for query in ("영상", "IT·기술", "기획"):
        response = await people_client.get("/api/v1/people", params={"q": query})
        assert response.json()["pagination"]["total"] == 1
        assert response.json()["data"][0]["accountId"] == str(PUBLIC_ID)
    filtered = await people_client.get(
        "/api/v1/people?fieldCode=design&roleCode=development"
    )
    assert filtered.json()["pagination"]["total"] == 1
    assert len(filtered.json()["data"]) == 1


async def test_search_treats_sql_wildcards_as_literal_and_empty_page_is_one(
    people_database: Database, people_client: AsyncClient
) -> None:
    await add_profile(people_database, PUBLIC_ID, name="일반 사용자")
    response = await people_client.get("/api/v1/people", params={"q": "%_", "page": 99})
    assert response.json()["data"] == []
    assert response.json()["pagination"] == {
        "page": 1,
        "pageSize": 20,
        "total": 0,
        "totalPages": 0,
    }


async def test_private_and_missing_people_are_indistinguishable_but_owner_can_read(
    people_database: Database, people_client: AsyncClient
) -> None:
    await add_profile(people_database, ACCOUNT_ID, public=False)
    private = await people_client.get(f"/api/v1/people/{ACCOUNT_ID}")
    missing = await people_client.get(f"/api/v1/people/{uuid4()}")
    assert private.status_code == missing.status_code == 404
    assert private.json()["error"] == missing.json()["error"]

    own = await people_client.get("/api/v1/me/profile")
    assert own.status_code == 200
    assert own.json()["data"]["isPublic"] is False
    assert own.json()["data"]["version"] == "1"
    assert own.json()["data"]["academicUnitId"] is None
    assert own.json()["data"]["portfolio"] is None
    assert set(own.json()["data"]) == {
        "accountId",
        "version",
        "isPublic",
        "isDemo",
        "updatedAt",
        "realName",
        "profileImageCode",
        "academicStatusCode",
        "gradeCode",
        "weeklyAvailabilityCode",
        "academicUnitId",
        "experienceState",
        "experienceBody",
        "introduction",
        "fieldCodes",
        "roleCodes",
        "skillCodes",
        "portfolio",
    }


async def test_missing_own_profile_is_404(people_client: AsyncClient) -> None:
    response = await people_client.get("/api/v1/me/profile")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page=9007199254740992",
        "pageSize=101",
        "page_size=1",
        "unknown=1",
        "fieldCode=unknown",
    ],
)
async def test_people_rejects_invalid_queries(
    people_client: AsyncClient, query: str
) -> None:
    response = await people_client.get(f"/api/v1/people?{query}")
    assert response.status_code == 422


async def test_public_profile_order_uses_updated_time_before_uuid(
    people_database: Database, people_client: AsyncClient
) -> None:
    await add_profile(people_database, PUBLIC_ID)
    await add_profile(
        people_database,
        DEMO_ID,
        updated_at=datetime(2026, 10, 24, tzinfo=UTC) + timedelta(seconds=1),
    )
    response = await people_client.get("/api/v1/people")
    assert [item["accountId"] for item in response.json()["data"]] == [
        str(DEMO_ID),
        str(PUBLIC_ID),
    ]


async def test_all_profile_read_routes_require_authentication(
    people_database: Database,
) -> None:
    app = FastAPI()
    app.state.database = people_database
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in (
            "/api/v1/people",
            f"/api/v1/people/{PUBLIC_ID}",
            "/api/v1/me/profile",
        ):
            response = await client.get(path)
            assert response.status_code == 401


async def test_real_session_authenticates_reads_without_sharing_query_transaction(
    people_database: Database,
) -> None:
    await add_profile(people_database, ACCOUNT_ID, public=False)
    async with people_database.session() as session:
        issued = await issue_session(session, ACCOUNT_ID)
        await session.commit()
    app = FastAPI()
    app.state.database = people_database
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, issued.token)
        own = await client.get("/api/v1/me/profile")
        assert own.status_code == 200
        assert own.json()["data"]["accountId"] == str(ACCOUNT_ID)
        assert (await client.get("/api/v1/people")).status_code == 200
        async with people_database.session() as session:
            await session.execute(
                update(AuthSession)
                .where(AuthSession.auth_session_id == issued.session.auth_session_id)
                .values(revoked_at=datetime.now(UTC))
            )
            await session.commit()
        assert (await client.get("/api/v1/me/profile")).status_code == 401


async def test_count_and_page_keep_the_same_snapshot_during_visibility_change(
    people_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add_profile(people_database, PUBLIC_ID)
    async with people_database.session() as reader:
        original_scalar = reader.scalar

        async def count_then_revoke_visibility(
            statement: Select[tuple[int]],
        ) -> int | None:
            total = await original_scalar(statement)
            async with people_database.session() as writer:
                await writer.execute(
                    update(metadata.tables["profiles"])
                    .where(metadata.tables["profiles"].c.profile_id == PUBLIC_ID)
                    .values(is_public=False)
                )
                await writer.commit()
            return total

        monkeypatch.setattr(reader, "scalar", count_then_revoke_visibility)
        result = await service.list_people(reader, PeopleQuery())
        assert result.pagination.total == len(result.data) == 1
        assert result.data[0].account_id == PUBLIC_ID
    async with people_database.session() as fresh_reader:
        result = await service.list_people(fresh_reader, PeopleQuery())
        assert result.pagination.total == 0
        assert result.data == []


async def test_public_detail_preserves_nullable_fields_and_bigint_identifiers(
    people_database: Database, people_client: AsyncClient
) -> None:
    await add_profile(people_database, PUBLIC_ID)
    async with people_database.session() as session:
        academic_unit = AcademicUnit(name="예시 대학")
        session.add(academic_unit)
        await session.flush()
        academic_id = academic_unit.academic_unit_id
        await session.execute(
            update(metadata.tables["profiles"])
            .where(metadata.tables["profiles"].c.profile_id == PUBLIC_ID)
            .values(
                academic_unit_id=academic_id,
                version=9223372036854775807,
                experience_state="provided",
                experience_body="프로젝트 경험",
            )
        )
        await session.execute(
            insert(metadata.tables["portfolio_links"]).values(
                portfolio_link_id=PUBLIC_ID,
                url="https://example.org/portfolio",
                title=None,
            )
        )
        await session.commit()
    response = await people_client.get(f"/api/v1/people/{PUBLIC_ID}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["academicUnitId"] == str(academic_id)
    assert data["version"] == "9223372036854775807"
    assert data["portfolio"] == {"url": "https://example.org/portfolio", "title": None}
    assert data["experienceState"] == "provided"
    assert data["experienceBody"] == "프로젝트 경험"
    assert data["updatedAt"].endswith("Z")


@pytest.mark.parametrize("scheme", ["http", "https"])
async def test_profile_details_preserve_long_portfolio_urls(
    people_database: Database, people_client: AsyncClient, scheme: str
) -> None:
    await add_profile(people_database, ACCOUNT_ID)
    prefix = f"{scheme}://example.org/portfolio/"
    long_url = prefix + "x" * (2129 - len(prefix))
    async with people_database.session() as session:
        session.add(
            PortfolioLink(
                portfolio_link_id=ACCOUNT_ID,
                url=long_url,
                title=None,
            )
        )
        await session.commit()

    for path in ("/api/v1/me/profile", f"/api/v1/people/{ACCOUNT_ID}"):
        response = await people_client.get(path)
        assert response.status_code == 200
        assert response.json()["data"]["portfolio"] == {
            "url": long_url,
            "title": None,
        }


async def test_authorized_batch_keeps_each_profiles_selections_and_portfolio(
    people_database: Database,
) -> None:
    await add_profile(people_database, ACCOUNT_ID, public=False, fields=("design",))
    await add_profile(
        people_database, PUBLIC_ID, roles=("planning",), skills=("document_writing",)
    )
    async with people_database.session() as session:
        session.add(
            PortfolioLink(
                portfolio_link_id=ACCOUNT_ID,
                url="https://example.org/owner",
                title=None,
            )
        )
        await session.commit()
        profiles = (await session.scalars(select(Profile))).all()
        result = await queries.build_profile_responses(session, profiles)
        owner = result[ACCOUNT_ID]
        person = result[PUBLIC_ID]
        assert owner.is_public is False
        assert owner.field_codes == ["design"]
        assert owner.portfolio is not None
        assert str(owner.portfolio.url) == "https://example.org/owner"
        assert person.field_codes == ["it_technology"]
        assert person.role_codes == ["planning"]
        assert person.skill_codes == ["document_writing"]
        assert person.portfolio is None


async def test_generated_contract_exposes_camelcase_queries_and_response_fields(
    people_client: AsyncClient,
) -> None:
    document = (await people_client.get("/openapi.json")).json()
    operation = document["paths"]["/api/v1/people"]["get"]
    assert {parameter["name"] for parameter in operation["parameters"]} == {
        "q",
        "fieldCode",
        "roleCode",
        "page",
        "pageSize",
    }
    assert set(document["components"]["schemas"]["ProfileResponse"]["required"]) == {
        "accountId",
        "version",
        "isPublic",
        "isDemo",
        "updatedAt",
        "realName",
        "profileImageCode",
        "academicStatusCode",
        "gradeCode",
        "weeklyAvailabilityCode",
        "academicUnitId",
        "experienceState",
        "experienceBody",
        "introduction",
        "fieldCodes",
        "roleCodes",
        "skillCodes",
        "portfolio",
    }


async def test_people_search_rejects_nul_before_database_lookup(
    people_client: AsyncClient,
) -> None:
    response = await people_client.get("/api/v1/people", params={"q": "검색\x00어"})
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["query", "q"]
