"""격리 PostgreSQL·실제 세션으로 본인 알림 조회와 읽음 권한을 검증한다."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import Result, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlalchemy.sql import Executable

from app.core.config import Settings
from app.core.db.base import Base
from app.core.db.session import Database
from app.core.http.handlers import register_error_handlers
from app.domains.applications.models import ApplicationEvent
from app.domains.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, issue_csrf_token
from app.domains.auth.dependencies import SESSION_COOKIE_NAME
from app.domains.auth.models import Account
from app.domains.auth.session_service import issue_session
from app.domains.notifications.models import Notification
from app.domains.notifications.router import router
from app.domains.notifications.service import list_notifications
from tests.integration.test_team_integrity import application, contest, team

pytestmark = [pytest.mark.integration, pytest.mark.database]
NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)
SIGNING_KEY = "notification-integration-key-32-bytes"


@dataclass(frozen=True)
class NotificationData:
    database: Database
    app: FastAPI
    account_id: UUID
    other_account_id: UUID
    owned_ids: tuple[UUID, ...]
    other_id: UUID
    token: str
    csrf: str


@pytest_asyncio.fixture
async def notification_data(database_url: str) -> AsyncIterator[NotificationData]:
    schema = f"notifications_test_{uuid4().hex}"
    engine = create_async_engine(
        database_url, execution_options={"schema_translate_map": {None: schema}}
    )
    database = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    app = FastAPI()
    app.state.database = database
    app.state.settings = Settings(
        csrf_signing_key=SecretStr(SIGNING_KEY),
        auth_allowed_origins=("https://testserver",),
        _env_file=None,
    )
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    try:
        async with engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            table_names = (
                "accounts",
                "auth_sessions",
                "contests",
                "teams",
                "applications",
                "team_memberships",
                "application_events",
                "notifications",
            )
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync, tables=[Base.metadata.tables[name] for name in table_names]
                )
            )
        async with database.session() as session:
            owner = Account(
                login_id_normalized="notifyowner", password_hash="test-only"
            )
            other = Account(
                login_id_normalized="notifyleader", password_hash="test-only"
            )
            parent_contest = contest()
            session.add_all([owner, other, parent_contest])
            await session.flush()
            first_team = team(parent_contest.contest_id, other.account_id)
            second_team = team(parent_contest.contest_id, other.account_id)
            session.add_all([first_team, second_team])
            await session.flush()
            first = application(
                first_team.team_id, parent_contest.contest_id, owner.account_id
            )
            second = application(
                second_team.team_id, parent_contest.contest_id, owner.account_id
            )
            first.status, first.version = "reviewing", 2
            session.add_all([first, second])
            await session.flush()
            events = [
                ApplicationEvent(
                    application_id=first.application_id,
                    team_id=first.team_id,
                    contest_id=first.contest_id,
                    applicant_account_id=owner.account_id,
                    application_version=1,
                    from_status=None,
                    to_status="submitted",
                    actor_account_id=owner.account_id,
                    reason_code="submitted",
                    occurred_at=NOW,
                ),
                ApplicationEvent(
                    application_id=first.application_id,
                    team_id=first.team_id,
                    contest_id=first.contest_id,
                    applicant_account_id=owner.account_id,
                    application_version=2,
                    from_status="submitted",
                    to_status="reviewing",
                    actor_account_id=other.account_id,
                    reason_code="reviewing_started",
                    occurred_at=NOW + timedelta(seconds=1),
                ),
                ApplicationEvent(
                    application_id=second.application_id,
                    team_id=second.team_id,
                    contest_id=second.contest_id,
                    applicant_account_id=owner.account_id,
                    application_version=1,
                    from_status=None,
                    to_status="submitted",
                    actor_account_id=owner.account_id,
                    reason_code="submitted",
                    occurred_at=NOW + timedelta(seconds=1),
                ),
            ]
            session.add_all(events)
            await session.flush()
            ids = (UUID(int=10), UUID(int=20), UUID(int=30))
            session.add_all(
                [
                    Notification(
                        notification_id=notification_id,
                        event_id=event.application_event_id,
                        recipient_account_id=owner.account_id,
                        kind="application_status_changed",
                        read_at=NOW + timedelta(seconds=2) if index == 1 else None,
                    )
                    for index, (notification_id, event) in enumerate(
                        zip(ids, events, strict=True)
                    )
                ]
            )
            other_id = UUID(int=40)
            session.add(
                Notification(
                    notification_id=other_id,
                    event_id=events[0].application_event_id,
                    recipient_account_id=other.account_id,
                    kind="new_application",
                )
            )
            issued = await issue_session(session, owner.account_id)
            csrf = issue_csrf_token(SIGNING_KEY, issued.session.token_hash)
            await session.commit()
            yield NotificationData(
                database,
                app,
                owner.account_id,
                other.account_id,
                ids,
                other_id,
                issued.token,
                csrf,
            )
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


@pytest_asyncio.fixture
async def notification_client(
    notification_data: NotificationData,
) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=notification_data.app, raise_app_exceptions=False),
        base_url="https://testserver",
        cookies={
            SESSION_COOKIE_NAME: notification_data.token,
            CSRF_COOKIE_NAME: notification_data.csrf,
        },
        headers={
            "Origin": "https://testserver",
            CSRF_HEADER_NAME: notification_data.csrf,
        },
    ) as client:
        yield client


async def test_list_preserves_history_orders_and_corrects_pages(
    notification_client: AsyncClient, notification_data: NotificationData
) -> None:
    response = await notification_client.get(
        "/api/v1/me/notifications", params={"page": 99, "pageSize": 2}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"] == {"page": 2, "pageSize": 2, "total": 3, "totalPages": 2}
    assert body["unreadCount"] == 2
    assert [item["id"] for item in body["data"]] == [
        str(notification_data.owned_ids[0])
    ]
    assert body["data"][0]["eventStatus"] == "submitted"
    assert body["data"][0]["readAt"] is None
    first_page = (
        await notification_client.get(
            "/api/v1/me/notifications", params={"pageSize": 2}
        )
    ).json()
    assert [item["id"] for item in first_page["data"]] == [
        str(notification_data.owned_ids[2]),
        str(notification_data.owned_ids[1]),
    ]


async def test_unread_filter_counts_all_owned_unread_without_marking_read(
    notification_client: AsyncClient, notification_data: NotificationData
) -> None:
    response = await notification_client.get(
        "/api/v1/me/notifications", params={"unreadOnly": "true", "pageSize": 1}
    )
    body = response.json()
    assert body["pagination"]["total"] == 2
    assert len(body["data"]) == 1
    assert body["unreadCount"] == 2
    assert (
        await notification_client.get("/api/v1/me/notifications/unread-count")
    ).json() == {"data": {"unreadCount": 2}}
    assert str(notification_data.other_id) not in response.text


async def test_notifications_reject_unauthenticated_and_invalid_pagination(
    notification_client: AsyncClient, notification_data: NotificationData
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=notification_data.app),
        base_url="https://testserver",
    ) as anonymous:
        for path in (
            "/api/v1/me/notifications",
            "/api/v1/me/notifications/unread-count",
        ):
            assert (await anonymous.get(path)).status_code == 401
    for params in (
        {"page": 0},
        {"page": 9007199254740992},
        {"pageSize": 101},
        {"unreadOnly": "unknown"},
    ):
        assert (
            await notification_client.get("/api/v1/me/notifications", params=params)
        ).status_code == 422


async def test_empty_owned_inbox_has_zero_metadata(
    notification_data: NotificationData,
) -> None:
    async with notification_data.database.session() as session:
        page = await list_notifications(session, uuid4(), page=99)
    assert page.data == []
    assert page.pagination.model_dump(mode="json") == {
        "page": 1,
        "pageSize": 20,
        "total": 0,
        "totalPages": 0,
    }
    assert page.unread_count == 0


async def test_counts_and_rows_keep_one_snapshot_during_concurrent_reading(
    notification_data: NotificationData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with notification_data.database.session() as session:
        execute = session.execute

        async def read_then_concurrent_change(
            statement: Executable,
        ) -> Result[tuple[object, ...]]:
            result = await execute(statement)
            async with notification_data.database.session() as writer:
                await writer.execute(
                    update(Notification)
                    .where(
                        Notification.recipient_account_id
                        == notification_data.account_id
                    )
                    .values(read_at=NOW + timedelta(seconds=3))
                )
                await writer.commit()
            return cast(Result[tuple[object, ...]], result)

        monkeypatch.setattr(session, "execute", read_then_concurrent_change)
        page = await list_notifications(
            session, notification_data.account_id, unread_only=True
        )
    assert len(page.data) == page.pagination.total == page.unread_count == 2
    assert all(item.read_at is None for item in page.data)
    async with notification_data.database.session() as fresh:
        refreshed = await list_notifications(
            fresh, notification_data.account_id, unread_only=True
        )
    assert refreshed.data == []
    assert refreshed.unread_count == refreshed.pagination.total == 0
