"""실제 PostgreSQL에서 과목 검색·재적재·프로필 연결 계약을 검증한다."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import Database
from app.core.http.handlers import register_error_handlers
from app.models.courses import Course, ProfileCourse
from app.repositories import courses as repository
from app.routers.catalogs import router
from app.schemas.course_import import CourseImport
from app.services.courses import import_courses
from tests.integration.test_profile_write import ACCOUNT
from tests.unit.test_profile_write import payload

pytest_plugins = ["tests.integration.test_profile_write"]
pytestmark = [pytest.mark.integration, pytest.mark.database]


def catalog(name: str = "자료구조") -> CourseImport:
    return CourseImport.model_validate(
        {
            "schema_version": "0.1.0",
            "courses": [
                {
                    "code": "CS1001",
                    "name": name,
                    "aliases": ["데이터 구조"],
                    "departments": ["컴퓨터공학과"],
                },
                {
                    "code": "CS1002",
                    "name": "알고리즘",
                    "aliases": [],
                    "departments": ["소프트웨어학과"],
                },
                {
                    "code": "GE1000",
                    "name": "100%_실습",
                    "aliases": [],
                    "departments": [],
                },
            ],
        }
    )


@pytest.fixture
async def catalog_client(people_database: Database) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.state.database = people_database
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def test_catalog_search_paging_aliases_and_literal_wildcards(
    people_database: Database, catalog_client: AsyncClient
) -> None:
    async with people_database.session() as session:
        await import_courses(session, catalog())
    for query in ("cs1001", "자료", "데이터 구조"):
        response = await catalog_client.get(
            "/api/v1/catalogs/courses", params={"q": query}
        )
        assert response.status_code == 200
        assert [item["code"] for item in response.json()["data"]] == ["CS1001"]
        assert response.json()["data"][0]["departments"] == ["컴퓨터공학과"]
    response = await catalog_client.get("/api/v1/catalogs/courses", params={"q": "%_"})
    assert [item["code"] for item in response.json()["data"]] == ["GE1000"]
    page = await catalog_client.get("/api/v1/catalogs/courses?page=999&pageSize=2")
    assert page.json()["pagination"] == {
        "page": 2,
        "pageSize": 2,
        "total": 3,
        "totalPages": 2,
    }
    assert page.json()["data"][0]["code"] == "GE1000"
    empty = await catalog_client.get("/api/v1/catalogs/courses?q=없음&page=99")
    assert empty.json() == {
        "data": [],
        "pagination": {"page": 1, "pageSize": 20, "total": 0, "totalPages": 0},
    }
    for query in ("page_size=5", "pageSize=101", "q=%00"):
        assert (
            await catalog_client.get("/api/v1/catalogs/courses?" + query)
        ).status_code == 422


async def test_profile_courses_replace_omit_clear_and_reject_unknown(
    people_database: Database, writer: AsyncClient
) -> None:
    async with people_database.session() as session:
        await import_courses(session, catalog())
    response = await writer.put(
        "/api/v1/me/profile", json=payload() | {"courseCodes": ["CS1002", "CS1001"]}
    )
    assert response.status_code == 200, response.text
    courses = [
        {"code": "CS1001", "name": "자료구조"},
        {"code": "CS1002", "name": "알고리즘"},
    ]
    assert response.json()["data"]["courses"] == courses
    retained = await writer.put(
        "/api/v1/me/profile", json=payload() | {"expectedVersion": "1"}
    )
    assert retained.json()["data"]["courses"] == courses
    failed = await writer.put(
        "/api/v1/me/profile",
        json=payload()
        | {
            "expectedVersion": "2",
            "realName": "저장되면 안 됨",
            "courseCodes": ["UNKNOWN"],
        },
    )
    assert failed.status_code == 409
    assert failed.json()["error"]["code"] == "INVALID_COURSE_SELECTION"
    unchanged = (await writer.get("/api/v1/me/profile")).json()["data"]
    assert (
        unchanged["courses"] == courses
        and unchanged["version"] == "2"
        and unchanged["realName"] == "가"
    )
    assert (await writer.get(f"/api/v1/people/{ACCOUNT}")).status_code == 404
    public = await writer.put(
        "/api/v1/me/profile/visibility", json={"expectedVersion": "2", "isPublic": True}
    )
    assert public.json()["data"]["courses"] == courses
    assert (await writer.get(f"/api/v1/people/{ACCOUNT}")).json()["data"][
        "courses"
    ] == courses
    cleared = await writer.put(
        "/api/v1/me/profile",
        json=payload() | {"expectedVersion": "3", "courseCodes": []},
    )
    assert cleared.json()["data"]["courses"] == []


async def test_reimport_is_idempotent_and_keeps_profile_links(
    people_database: Database, writer: AsyncClient
) -> None:
    async with people_database.session() as session:
        assert await import_courses(session, catalog()) == {
            "created": 3,
            "updated": 0,
            "unchanged": 0,
        }
        original_id = await session.scalar(
            select(Course.course_id).where(Course.code == "CS1001")
        )
    await writer.put("/api/v1/me/profile", json=payload() | {"courseCodes": ["CS1001"]})
    async with people_database.session() as session:
        assert await import_courses(session, catalog()) == {
            "created": 0,
            "updated": 0,
            "unchanged": 3,
        }
        revised = catalog("자료구조실습")
        revised.courses = revised.courses[:1]
        assert await import_courses(session, revised) == {
            "created": 0,
            "updated": 1,
            "unchanged": 0,
        }
        assert await session.scalar(select(func.count()).select_from(Course)) == 3
        assert await session.scalar(select(ProfileCourse.course_id)) == original_id
    assert (await writer.get("/api/v1/me/profile")).json()["data"]["courses"] == [
        {"code": "CS1001", "name": "자료구조실습"}
    ]


async def test_concurrent_imports_do_not_duplicate_courses(
    people_database: Database,
) -> None:
    async def load() -> dict[str, int]:
        async with people_database.session() as session:
            return await import_courses(session, catalog())

    results = await asyncio.gather(load(), load())
    assert sorted(result["created"] for result in results) == [0, 3]
    assert sorted(result["unchanged"] for result in results) == [0, 3]


async def test_import_failure_rolls_back_entire_catalog(
    people_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = repository.store_courses

    async def fail(session: AsyncSession, courses: Sequence[Course]) -> None:
        await original(session, courses)
        raise RuntimeError("injected failure after flush")

    monkeypatch.setattr(repository, "store_courses", fail)
    async with people_database.session() as session:
        with pytest.raises(RuntimeError):
            await import_courses(session, catalog())
    async with people_database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Course)) == 0


async def test_profile_course_failure_keeps_existing_profile_and_selection(
    people_database: Database, writer: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with people_database.session() as session:
        await import_courses(session, catalog())
    created = await writer.put(
        "/api/v1/me/profile", json=payload() | {"courseCodes": ["CS1001"]}
    )
    assert created.status_code == 200
    original = repository.replace_profile_courses

    async def fail(
        session: AsyncSession, account_id: UUID, courses: Sequence[Course]
    ) -> None:
        await original(session, account_id, courses)
        raise RuntimeError("injected failure after course replacement")

    monkeypatch.setattr(repository, "replace_profile_courses", fail)
    response = await writer.put(
        "/api/v1/me/profile",
        json=payload()
        | {
            "expectedVersion": "1",
            "realName": "저장되면 안 됨",
            "courseCodes": ["CS1002"],
        },
    )
    assert response.status_code == 500
    assert (await writer.get("/api/v1/me/profile")).json() == created.json()
