"""본인·받은 팀장만 지원을 조회하고 다른 지원의 폐기 원인을 숨기는지 검증한다."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.domains.applications.models import Application, ApplicationEvent
from app.domains.notifications.models import Notification
from app.domains.teams.models import Team, TeamMembership
from tests.integration.application_support import (
    ApplicationData,
    application_client,
    make_application,
)
from tests.integration.application_support import application_data as application_data

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def test_only_applicant_and_receiving_leader_can_read(
    application_data: ApplicationData,
) -> None:
    data = application_data
    path = f"/api/v1/applications/{data.application_id}"
    for viewer in (data.applicant_id, data.leader_id):
        async with application_client(data, viewer) as client:
            response = await client.get(path)
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["applicantAccountId"] == str(data.applicant_id)
        assert body["status"] == "submitted" and body["version"] == "1"
        assert body["message"] == "함께 참여하겠습니다."
        assert body["discardedByApplicationId"] is None
        assert body["discardedByTeamId"] is None
        assert "profile" not in body and "requestFingerprint" not in body
    async with application_client(data, data.stranger_id) as client:
        denied = await client.get(path)
        missing = await client.get(f"/api/v1/applications/{uuid4()}")
        assert denied.status_code == missing.status_code == 404
        assert denied.json()["error"] == missing.json()["error"]
    async with application_client(data, None) as client:
        assert (await client.get(path)).status_code == 401
    async with data.database.session() as session:
        application = await session.get(Application, data.application_id)
        assert application is not None and application.status == "submitted"
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationEvent))
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(Notification)) == 0


@pytest.mark.parametrize("cause", ["selected_elsewhere", "team_created_elsewhere"])
async def test_discard_cause_identity_is_visible_only_to_applicant(
    application_data: ApplicationData, cause: str
) -> None:
    data = application_data
    now = datetime.now(UTC)
    async with data.database.session() as session:
        target = await session.get(Application, data.application_id)
        assert target is not None
        target.status = "discarded"
        target.version = 2
        target.status_changed_at = now
        cause_event_id = None
        cause_membership_id = None
        source_application_id = None
        if cause == "selected_elsewhere":
            source = make_application(
                data.other_team_id, data.contest_id, data.applicant_id, now
            )
            source.status = "selected"
            source.version = 2
            session.add(source)
            await session.flush()
            source_application_id = source.application_id
            source_event = ApplicationEvent(
                application_event_id=uuid4(),
                application_id=source.application_id,
                team_id=data.other_team_id,
                contest_id=data.contest_id,
                applicant_account_id=data.applicant_id,
                application_version=2,
                from_status="submitted",
                to_status="selected",
                actor_account_id=data.stranger_id,
                reason_code="selected",
                occurred_at=now,
            )
            session.add(source_event)
            await session.flush()
            cause_event_id = source_event.application_event_id
        else:
            source_team = await session.get(Team, data.other_team_id)
            assert source_team is not None
            source_team.leader_account_id = data.applicant_id
            membership = TeamMembership(
                team_membership_id=uuid4(),
                team_id=data.other_team_id,
                contest_id=data.contest_id,
                account_id=data.applicant_id,
                joined_at=now,
            )
            session.add(membership)
            await session.flush()
            cause_membership_id = membership.team_membership_id
        session.add(
            ApplicationEvent(
                application_id=data.application_id,
                team_id=data.team_id,
                contest_id=data.contest_id,
                applicant_account_id=data.applicant_id,
                application_version=2,
                from_status="submitted",
                to_status="discarded",
                actor_account_id=None,
                reason_code=cause,
                cause_event_id=cause_event_id,
                cause_membership_id=cause_membership_id,
                occurred_at=now,
            )
        )
        await session.commit()
    for viewer in (data.applicant_id, data.leader_id):
        async with application_client(data, viewer) as client:
            response = await client.get(f"/api/v1/applications/{data.application_id}")
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["discardReason"] == cause
        expected_application = (
            str(source_application_id)
            if viewer == data.applicant_id and source_application_id
            else None
        )
        expected_team = (
            str(data.other_team_id)
            if viewer == data.applicant_id and cause == "team_created_elsewhere"
            else None
        )
        assert body["discardedByApplicationId"] == expected_application
        assert body["discardedByTeamId"] == expected_team
