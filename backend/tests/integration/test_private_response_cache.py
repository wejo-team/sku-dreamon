"""실제 세션의 개인 응답·권한 변화가 HTTP 캐시에 저장되지 않도록 검증한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from pydantic import SecretStr
from sqlalchemy import select, update

from app.core.config import Settings
from app.core.http.handlers import register_error_handlers
from app.dependencies.auth import SESSION_COOKIE_NAME
from app.dependencies.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.models.applications import ApplicationEvent
from app.models.notifications import Notification
from app.models.profiles import Profile
from app.routers.application_review import router as review_router
from app.routers.applications import router as applications_router
from app.routers.auth import router as auth_router
from app.routers.contests import router as contests_router
from app.routers.notifications import router as notifications_router
from app.routers.profiles import router as profiles_router
from app.security.csrf import issue_csrf_token
from tests.integration.application_review_support import review_data as review_data
from tests.integration.application_support import ORIGIN, SIGNING_KEY, ApplicationData
from tests.integration.application_support import application_data as application_data

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest.fixture
async def private_data(review_data: ApplicationData) -> ApplicationData:
    data = review_data
    async with data.database.session() as session:
        await session.execute(
            update(Profile)
            .where(Profile.profile_id == data.applicant_id)
            .values(is_public=True)
        )
        event_id = await session.scalar(
            select(ApplicationEvent.application_event_id).where(
                ApplicationEvent.application_id == data.application_id
            )
        )
        assert event_id is not None
        session.add(
            Notification(
                event_id=event_id,
                recipient_account_id=data.applicant_id,
                kind="application_status_changed",
            )
        )
        await session.commit()
    return data


@asynccontextmanager
async def private_client(
    data: ApplicationData, account_id: UUID | None = None
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.state.database = data.database
    app.state.settings = Settings(
        csrf_signing_key=SecretStr(SIGNING_KEY),
        auth_allowed_origins=(ORIGIN,),
        _env_file=None,
    )
    register_error_handlers(app)
    for router in (
        auth_router,
        profiles_router,
        applications_router,
        review_router,
        notifications_router,
        contests_router,
    ):
        app.include_router(router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url=ORIGIN
    ) as client:
        if account_id is not None:
            issued = data.sessions[account_id]
            client.cookies.set(SESSION_COOKIE_NAME, issued.token)
            csrf = issue_csrf_token(SIGNING_KEY, issued.session.token_hash)
            client.cookies.set(CSRF_COOKIE_NAME, csrf)
            client.headers.update({CSRF_HEADER_NAME: csrf, "Origin": ORIGIN})
        yield client


def assert_no_store(response: Response, status: int) -> None:
    assert response.status_code == status, response.text
    assert response.headers.get_list("cache-control") == ["no-store"]


@pytest.mark.parametrize(
    ("path", "actor"),
    [
        ("/me", "applicant"),
        ("/me/profile", "applicant"),
        ("/people", "stranger"),
        ("/people/{applicant_id}", "stranger"),
        ("/me/applications", "applicant"),
        ("/applications/{application_id}", "applicant"),
        ("/teams/{team_id}/applicants", "leader"),
        ("/applications/{application_id}/applicant", "leader"),
        ("/me/notifications", "applicant"),
        ("/me/notifications/unread-count", "applicant"),
    ],
)
async def test_private_gets_do_not_cache_success_or_revoked_sessions(
    private_data: ApplicationData, path: str, actor: str
) -> None:
    data = private_data
    path = "/api/v1" + path.format(
        applicant_id=data.applicant_id,
        application_id=data.application_id,
        team_id=data.team_id,
    )
    async with private_client(data) as anonymous:
        assert_no_store(await anonymous.get(path), 401)
    account_id = {
        "applicant": data.applicant_id,
        "leader": data.leader_id,
        "stranger": data.stranger_id,
    }[actor]
    async with private_client(data, account_id) as client:
        success = await client.get(path)
        assert_no_store(success, 200)
        assert success.json()["data"]
        logout = await client.post("/api/v1/auth/logout")
        assert_no_store(logout, 204)
        assert not logout.content
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE_NAME, data.sessions[account_id].token)
        revoked = await client.get(path)
        assert_no_store(revoked, 401)
        assert revoked.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize(
    ("path", "actor", "status"),
    [
        ("/applications/{application_id}", "stranger", 404),
        ("/applications/{application_id}/applicant", "applicant", 403),
        ("/applications/{application_id}/applicant", "stranger", 404),
        ("/teams/{team_id}/applicants", "stranger", 403),
        ("/teams/{missing_id}/applicants", "leader", 404),
        ("/people/{missing_id}", "stranger", 404),
        ("/people?page=0", "stranger", 422),
    ],
)
async def test_private_denials_and_validation_errors_are_not_cached(
    private_data: ApplicationData, path: str, actor: str, status: int
) -> None:
    data = private_data
    path = "/api/v1" + path.format(
        application_id=data.application_id, team_id=data.team_id, missing_id=uuid4()
    )
    account_id = {
        "applicant": data.applicant_id,
        "leader": data.leader_id,
        "stranger": data.stranger_id,
    }[actor]
    async with private_client(data, account_id) as client:
        response = await client.get(path)
    assert_no_store(response, status)
    assert "profile" not in response.json() and "data" not in response.json()


async def test_visibility_change_removes_public_profile_but_keeps_leader_access(
    private_data: ApplicationData,
) -> None:
    data = private_data
    path = f"/api/v1/people/{data.applicant_id}"
    async with (
        private_client(data, data.stranger_id) as viewer,
        private_client(data, data.applicant_id) as owner,
        private_client(data, data.leader_id) as leader,
    ):
        before = await viewer.get(path)
        assert_no_store(before, 200)
        assert before.json()["data"]["isPublic"] is True
        changed = await owner.put(
            "/api/v1/me/profile/visibility",
            json={"expectedVersion": "1", "isPublic": False},
        )
        assert_no_store(changed, 200)
        assert changed.json()["data"]["isPublic"] is False
        assert_no_store(await viewer.get(path), 404)
        listing = await viewer.get("/api/v1/people")
        assert_no_store(listing, 200)
        assert listing.json()["data"] == []
        own = await owner.get("/api/v1/me/profile")
        assert_no_store(own, 200)
        assert own.json()["data"] == changed.json()["data"]
        applicant = await leader.get(
            f"/api/v1/applications/{data.application_id}/applicant"
        )
        assert_no_store(applicant, 200)
        assert applicant.json()["data"]["profile"]["isPublic"] is False


async def test_public_contest_success_keeps_existing_cache_behavior(
    private_data: ApplicationData,
) -> None:
    data = private_data
    for viewer in (None, data.applicant_id):
        async with private_client(data, viewer) as client:
            response = await client.get("/api/v1/contests")
            assert response.status_code == 200, response.text
            assert response.json()["data"][0]["id"] == str(data.contest_id)
            assert "cache-control" not in response.headers
