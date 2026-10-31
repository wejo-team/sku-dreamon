"""프로필 전체 저장·공개 전환의 HTTP 계약과 동시성·롤백을 검증한다."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db.session import Database
from app.core.exceptions import AppError
from app.core.http.handlers import register_error_handlers
from app.dependencies.auth import SESSION_COOKIE_NAME
from app.models.auth import Account
from app.models.profiles import PortfolioLink, Profile
from app.repositories import profile_write as repository
from app.routers.auth import router as auth_router
from app.routers.profiles import router
from app.schemas.profile_write import ProfileWrite
from app.services.profile_write import save_profile
from app.services.sessions import issue_session
from tests.unit.test_profile_write import payload

pytest_plugins = ["tests.integration.test_people_api"]
pytestmark = [pytest.mark.integration, pytest.mark.database]
ACCOUNT = UUID(int=101)
ORIGIN = "https://profile.example.test"


@pytest.fixture
async def writer(people_database: Database) -> AsyncIterator[AsyncClient]:
    async with people_database.session() as session:
        session.add(
            Account(
                account_id=ACCOUNT,
                login_id_normalized="writer01",
                password_hash="test-hash",
            )
        )
        await session.flush()
        issued = await issue_session(session, ACCOUNT)
        await session.commit()
    app = FastAPI()
    app.state.database = people_database
    app.state.settings = Settings(
        csrf_signing_key=SecretStr("profile-write-key-32-bytes-long!!!"),
        auth_allowed_origins=(ORIGIN,),
        _env_file=None,
    )
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url=ORIGIN
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, issued.token)
        csrf = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrfToken"]
        client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
        yield client


async def test_create_edit_visibility_and_public_access(writer: AsyncClient) -> None:
    created = await writer.put("/api/v1/me/profile", json=payload())
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["realName"] == "가" and data["version"] == "1" and not data["isPublic"]
    assert (await writer.get(f"/api/v1/people/{ACCOUNT}")).status_code == 404
    public = await writer.put(
        "/api/v1/me/profile/visibility", json={"expectedVersion": "1", "isPublic": True}
    )
    assert public.json()["data"]["version"] == "2"
    assert (await writer.get(f"/api/v1/people/{ACCOUNT}")).status_code == 200
    unchanged = await writer.put(
        "/api/v1/me/profile/visibility", json={"expectedVersion": "2", "isPublic": True}
    )
    assert unchanged.json() == public.json()
    stale = await writer.put("/api/v1/me/profile", json=payload())
    assert stale.status_code == 409
    edited = await writer.put(
        "/api/v1/me/profile",
        json=payload()
        | {
            "expectedVersion": "2",
            "introduction": " 새 소개 ",
            "portfolio": {"url": "https://example.test/portfolio", "title": " 제목 "},
        },
    )
    assert edited.status_code == 200, edited.text
    data = edited.json()["data"]
    assert (
        data["isPublic"]
        and data["introduction"] == "새 소개"
        and data["version"] == "3"
    )
    assert data["portfolio"]["title"] == "제목"
    removed = await writer.put(
        "/api/v1/me/profile", json=payload() | {"expectedVersion": "3"}
    )
    assert removed.json()["data"]["portfolio"] is None
    assert (await writer.get("/api/v1/me/profile")).json() == removed.json()


async def test_invalid_catalog_academic_and_csrf_keep_profile(
    writer: AsyncClient,
) -> None:
    assert (
        await writer.put(
            "/api/v1/me/profile", json=payload() | {"fieldCodes": ["invalid"]}
        )
    ).status_code == 409
    assert (
        await writer.put(
            "/api/v1/me/profile", json=payload() | {"academicUnitId": "999999"}
        )
    ).status_code == 409
    assert (await writer.get("/api/v1/me/profile")).status_code == 404
    response = await writer.put(
        "/api/v1/me/profile", json=payload(), headers={"X-CSRF-Token": "bad"}
    )
    assert response.status_code == 403
    response = await writer.put(
        "/api/v1/me/profile", json=payload() | {"isPublic": True}
    )
    assert response.status_code == 422


async def test_concurrent_first_save_has_one_winner(
    writer: AsyncClient, people_database: Database
) -> None:
    async def save() -> int:
        async with people_database.session() as session:
            try:
                await save_profile(
                    session, ACCOUNT, ProfileWrite.model_validate(payload())
                )
                return 200
            except AppError as error:
                return error.status_code

    assert sorted(await asyncio.gather(save(), save())) == [200, 409]


async def test_selection_failure_preserves_all_previous_fields(
    writer: AsyncClient, people_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (await writer.put("/api/v1/me/profile", json=payload())).status_code == 200
    original = repository.replace_selections

    async def fail(
        session: AsyncSession,
        account_id: UUID,
        *,
        fields: Sequence[str],
        roles: Sequence[str],
        skills: Sequence[str],
        portfolio: PortfolioLink | None,
    ) -> None:
        await original(
            session,
            account_id,
            fields=fields,
            roles=roles,
            skills=skills,
            portfolio=portfolio,
        )
        raise RuntimeError("injected failure")

    monkeypatch.setattr(repository, "replace_selections", fail)
    failed = await writer.put(
        "/api/v1/me/profile",
        json=payload()
        | {
            "expectedVersion": "1",
            "realName": "바뀐 이름",
            "fieldCodes": ["it_technology"],
        },
    )
    assert failed.status_code == 500
    stored = (await writer.get("/api/v1/me/profile")).json()["data"]
    assert (
        stored["realName"] == "가"
        and stored["fieldCodes"] == ["design"]
        and stored["version"] == "1"
    )
    async with people_database.session() as session:
        assert len(list(await session.scalars(select(Profile)))) == 1
