"""팀장의 명시적 검토·미선발과 버전·권한·원자성을 검증한다."""

import pytest
from sqlalchemy import event, func, select

from app.domains.applications.models import Application, ApplicationEvent
from app.domains.auth.csrf import CSRF_HEADER_NAME
from app.domains.notifications.models import Notification
from app.domains.teams.models import Team, TeamMembership
from tests.integration.application_review_support import review_client
from tests.integration.application_review_support import review_data as review_data
from tests.integration.application_support import ApplicationData
from tests.integration.application_support import application_data as application_data

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest.mark.parametrize(
    "action,status", [("review-start", "reviewing"), ("rejection", "rejected")]
)
async def test_explicit_review_action_versions_notifications_and_noop(
    review_data: ApplicationData,
    action: str,
    status: str,
) -> None:
    data = review_data
    path = f"/api/v1/applications/{data.application_id}/{action}"
    async with review_client(data, data.leader_id) as client:
        changed = await client.put(path, json={"expectedVersion": "1"})
        assert changed.status_code == 200
        assert changed.json()["data"]["status"] == status
        assert changed.json()["data"]["version"] == "2"
        stale = await client.put(path, json={"expectedVersion": "1"})
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
        repeated = await client.put(path, json={"expectedVersion": "2"})
        assert repeated.json() == changed.json()
    async with data.database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationEvent))
            == 2
        )
        notices = (await session.scalars(select(Notification))).all()
        assert (
            len(notices) == 1 and notices[0].recipient_account_id == data.applicant_id
        )
        team = await session.get(Team, data.team_id)
        assert (
            team is not None and team.version == 1 and team.recruitment_state == "open"
        )
        assert (
            await session.scalar(select(func.count()).select_from(TeamMembership)) == 2
        )


async def test_rejection_follows_reviewing_and_cannot_be_reopened(
    review_data: ApplicationData,
) -> None:
    data = review_data
    base = f"/api/v1/applications/{data.application_id}"
    async with review_client(data, data.leader_id) as client:
        assert (
            await client.put(f"{base}/review-start", json={"expectedVersion": "1"})
        ).status_code == 200
        assert (
            await client.put(f"{base}/rejection", json={"expectedVersion": "2"})
        ).status_code == 200
        for version, code in (
            ("2", "VERSION_CONFLICT"),
            ("3", "INVALID_APPLICATION_STATE"),
        ):
            denied = await client.put(
                f"{base}/review-start", json={"expectedVersion": version}
            )
            assert denied.status_code == 409 and denied.json()["error"]["code"] == code


async def test_review_actions_require_receiving_leader_and_authenticated_csrf(
    review_data: ApplicationData,
) -> None:
    data = review_data
    for action in ("review-start", "rejection"):
        path = f"/api/v1/applications/{data.application_id}/{action}"
        for viewer, status in (
            (None, 401),
            (data.applicant_id, 403),
            (data.stranger_id, 404),
        ):
            async with review_client(data, viewer) as client:
                assert (
                    await client.put(path, json={"expectedVersion": "1"})
                ).status_code == status
        async with review_client(data, data.leader_id) as client:
            del client.headers[CSRF_HEADER_NAME]
            assert (
                await client.put(path, json={"expectedVersion": "1"})
            ).status_code == 403


async def test_failed_review_notification_rolls_back_status_version_and_event(
    review_data: ApplicationData,
) -> None:
    data = review_data

    def fail_notification(*args: object) -> None:
        raise RuntimeError("notification write unavailable")

    event.listen(Notification, "before_insert", fail_notification)
    try:
        async with review_client(data, data.leader_id) as client:
            result = await client.put(
                f"/api/v1/applications/{data.application_id}/rejection",
                json={"expectedVersion": "1"},
            )
            assert result.status_code == 500
    finally:
        event.remove(Notification, "before_insert", fail_notification)
    async with data.database.session() as session:
        application = await session.get(Application, data.application_id)
        assert (
            application is not None
            and application.status == "submitted"
            and application.version == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationEvent))
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(Notification)) == 0
