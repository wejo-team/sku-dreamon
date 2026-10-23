"""취소의 버전·권한·자리 반환·원자성과 실제 동시 요청을 검증한다."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from app.domains.applications.models import Application, ApplicationEvent
from app.domains.auth.csrf import CSRF_HEADER_NAME
from app.domains.auth.models import AuthSession
from app.domains.notifications.models import Notification
from app.domains.teams.models import Team, TeamMembership
from tests.integration.application_support import ApplicationData, application_client
from tests.integration.application_support import application_data as application_data

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def set_status(data: ApplicationData, status: str) -> None:
    async with data.database.session() as session:
        application = await session.get(Application, data.application_id)
        team = await session.get(Team, data.team_id)
        assert application is not None and team is not None
        now = datetime.now(UTC)
        application.status = status
        application.version = 2
        application.status_changed_at = now
        session.add(
            ApplicationEvent(
                application_id=data.application_id,
                team_id=data.team_id,
                contest_id=data.contest_id,
                applicant_account_id=data.applicant_id,
                application_version=2,
                from_status="submitted",
                to_status=status,
                actor_account_id=data.leader_id,
                reason_code="reviewing_started" if status == "reviewing" else status,
                occurred_at=now,
            )
        )
        if status == "selected":
            session.add(
                TeamMembership(
                    team_id=data.team_id,
                    contest_id=data.contest_id,
                    account_id=data.applicant_id,
                    source_application_id=data.application_id,
                    joined_at=now,
                )
            )
            team.recruitment_state = "closed"
            team.closed_reason = "capacity_reached"
        await session.commit()


@pytest.mark.parametrize("status", ["submitted", "reviewing", "selected"])
async def test_cancel_and_current_version_noop(
    application_data: ApplicationData,
    status: str,
) -> None:
    data = application_data
    if status != "submitted":
        await set_status(data, status)
    version = 1 if status == "submitted" else 2
    path = f"/api/v1/applications/{data.application_id}/cancellation"
    async with application_client(data, data.applicant_id) as client:
        response = await client.put(path, json={"expectedVersion": str(version)})
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["application"]["status"] == "canceled"
        assert body["application"]["version"] == str(version + 1)
        assert body["membershipEnded"] is (status == "selected")
        stale = await client.put(path, json={"expectedVersion": str(version)})
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
        repeated = await client.put(path, json={"expectedVersion": str(version + 1)})
        assert repeated.status_code == 200 and repeated.json() == response.json()
    async with data.database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationEvent))
            == version + 1
        )
        notices = list(await session.scalars(select(Notification)))
        assert (
            len(notices) == 1 and notices[0].recipient_account_id == data.applicant_id
        )
        team = await session.get(Team, data.team_id)
        assert team is not None
        assert team.version == (2 if status == "selected" else 1)
        if status == "selected":
            assert (
                team.recruitment_state == "closed"
                and team.closed_reason == "capacity_reached"
            )
            membership = await session.scalar(
                select(TeamMembership).where(
                    TeamMembership.source_application_id == data.application_id
                )
            )
            assert membership is not None and membership.ended_at is not None
            assert membership.end_reason == "application_canceled"
        else:
            assert team.recruitment_state == "open"


async def test_rejected_cannot_cancel_and_version_is_checked_first(
    application_data: ApplicationData,
) -> None:
    data = application_data
    await set_status(data, "rejected")
    async with application_client(data, data.applicant_id) as client:
        path = f"/api/v1/applications/{data.application_id}/cancellation"
        for version, code in (
            ("1", "VERSION_CONFLICT"),
            ("2", "INVALID_APPLICATION_STATE"),
        ):
            response = await client.put(path, json={"expectedVersion": version})
            assert (
                response.status_code == 409 and response.json()["error"]["code"] == code
            )


async def test_permission_csrf_and_strict_version(
    application_data: ApplicationData,
) -> None:
    data = application_data
    path = f"/api/v1/applications/{data.application_id}/cancellation"
    for viewer, status in ((data.leader_id, 403), (data.stranger_id, 404)):
        async with application_client(data, viewer) as client:
            assert (
                await client.put(path, json={"expectedVersion": "1"})
            ).status_code == status
    async with application_client(data, data.applicant_id) as client:
        for invalid in (
            {"expectedVersion": 1},
            {"expected_version": "1"},
            {"expectedVersion": "0"},
        ):
            assert (await client.put(path, json=invalid)).status_code == 422
        missing = await client.put(
            f"/api/v1/applications/{uuid4()}/cancellation",
            json={"expectedVersion": "1"},
        )
        assert missing.status_code == 404
        del client.headers[CSRF_HEADER_NAME]
        assert (
            await client.put(path, json={"expectedVersion": "1"})
        ).status_code == 403


async def test_anonymous_and_revoked_session_fail_auth_before_csrf(
    application_data: ApplicationData,
) -> None:
    data = application_data
    path = f"/api/v1/applications/{data.application_id}/cancellation"
    async with application_client(data, None) as client:
        assert (
            await client.put(path, json={"expectedVersion": "1"})
        ).status_code == 401
    async with data.database.session() as session:
        auth_session = await session.get(
            AuthSession, data.sessions[data.applicant_id].session.auth_session_id
        )
        assert auth_session is not None
        auth_session.revoked_at = datetime.now(UTC)
        await session.commit()
    async with application_client(data, data.applicant_id) as client:
        del client.headers[CSRF_HEADER_NAME]
        assert (
            await client.put(path, json={"expectedVersion": "1"})
        ).status_code == 401


async def test_notification_failure_rolls_back_membership_event_and_application(
    application_data: ApplicationData,
) -> None:
    data = application_data
    await set_status(data, "selected")

    def fail_notice(*args: object) -> None:
        raise RuntimeError("Injected notification write failure")

    event.listen(Notification, "before_insert", fail_notice)
    try:
        async with application_client(data, data.applicant_id) as client:
            response = await client.put(
                f"/api/v1/applications/{data.application_id}/cancellation",
                json={"expectedVersion": "2"},
            )
        assert response.status_code == 500
    finally:
        event.remove(Notification, "before_insert", fail_notice)
    async with data.database.session() as session:
        application = await session.get(Application, data.application_id)
        team = await session.get(Team, data.team_id)
        membership = await session.scalar(
            select(TeamMembership).where(
                TeamMembership.source_application_id == data.application_id
            )
        )
        assert (
            application is not None
            and application.status == "selected"
            and application.version == 2
        )
        assert team is not None and team.version == 1
        assert membership is not None and membership.ended_at is None
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationEvent))
            == 2
        )
        assert await session.scalar(select(func.count()).select_from(Notification)) == 0


async def test_concurrent_cancel_has_one_event_and_one_version_winner(
    application_data: ApplicationData,
) -> None:
    data = application_data
    await set_status(data, "selected")
    async with (
        application_client(data, data.applicant_id) as first,
        application_client(data, data.applicant_id) as second,
    ):
        path = f"/api/v1/applications/{data.application_id}/cancellation"
        responses = await asyncio.gather(
            first.put(path, json={"expectedVersion": "2"}),
            second.put(path, json={"expectedVersion": "2"}),
        )
    assert sorted(response.status_code for response in responses) == [200, 409]
    async with data.database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationEvent))
            == 3
        )
        assert await session.scalar(select(func.count()).select_from(Notification)) == 1
