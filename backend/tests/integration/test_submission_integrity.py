"""지원 생성의 동시 중복·실패 롤백·현재 모집 조건과 과거 재전송을 검증한다."""

import asyncio
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.applications import Application, ApplicationEvent
from app.models.contests import Contest
from app.models.notifications import Notification
from app.models.profiles import Profile
from app.models.teams import Team
from app.schemas.application_create import ApplicationCreate
from app.services import application_create as service
from app.services.applications import cancel_application
from app.services.notifications import create_notification as original_notification
from tests.integration.application_review_support import review_data as review_data
from tests.integration.application_support import ApplicationData
from tests.integration.application_support import application_data as application_data
from tests.integration.creation_support import creation_client
from tests.integration.test_application_submission import make_public

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def test_concurrent_same_request_has_one_event_pair(
    review_data: ApplicationData,
) -> None:
    await make_public(review_data)
    body = ApplicationCreate(requestId=uuid4(), roleCode="planning")

    async def submit() -> bool:
        async with review_data.database.session() as session:
            _, created = await service.submit_application(
                session, review_data.applicant_id, review_data.other_team_id, body
            )
            return created

    assert sorted(await asyncio.gather(submit(), submit())) == [False, True]
    async with review_data.database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Notification)) == 2
        with pytest.raises(AppError) as caught:
            await service.submit_application(
                session,
                review_data.applicant_id,
                review_data.other_team_id,
                ApplicationCreate(requestId=uuid4(), roleCode="planning"),
            )
        assert caught.value.code == "DUPLICATE_APPLICATION"


async def test_second_notification_failure_rolls_back_submission(
    review_data: ApplicationData, monkeypatch: pytest.MonkeyPatch
) -> None:
    await make_public(review_data)

    async def fail_second(
        session: AsyncSession,
        *,
        event_id: UUID,
        recipient_id: UUID,
        kind: Literal["application_status_changed", "new_application"],
    ) -> Notification:
        if kind == "new_application":
            raise RuntimeError("notification failure")
        return await original_notification(
            session, event_id=event_id, recipient_id=recipient_id, kind=kind
        )

    monkeypatch.setattr(service, "create_notification", fail_second)
    async with review_data.database.session() as session:
        with pytest.raises(RuntimeError):
            await service.submit_application(
                session,
                review_data.applicant_id,
                review_data.other_team_id,
                ApplicationCreate(requestId=uuid4(), roleCode="planning"),
            )
    async with review_data.database.session() as session:
        assert await session.scalar(select(func.count()).select_from(Notification)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Application)
                .where(Application.team_id == review_data.other_team_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ApplicationEvent)
                .where(ApplicationEvent.team_id == review_data.other_team_id)
            )
            == 0
        )


@pytest.mark.parametrize(
    "condition,code",
    [
        ("closed", "RECRUITMENT_CLOSED"),
        ("full", "TEAM_FULL"),
        ("deadline", "RECRUITMENT_DEADLINE_PASSED"),
        ("contest", "CONTEST_NOT_OPEN"),
    ],
)
async def test_current_recruitment_conditions(
    review_data: ApplicationData,
    condition: str,
    code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await make_public(review_data)
    async with review_data.database.session() as session:
        team = await session.get(Team, review_data.other_team_id)
        contest = await session.get(Contest, review_data.contest_id)
        assert team is not None and contest is not None
        if condition == "closed":
            team.recruitment_state, team.closed_reason = "closed", "leader_closed"
        elif condition == "full":
            team.target_capacity = 1
        else:
            moment: datetime = (
                team.recruitment_closes_at
                if condition == "deadline"
                else contest.registration_closes_at
            )
            monkeypatch.setattr(service, "_utcnow", lambda: moment)
        await session.commit()
    async with review_data.database.session() as session:
        with pytest.raises(AppError) as caught:
            await service.submit_application(
                session,
                review_data.applicant_id,
                review_data.other_team_id,
                ApplicationCreate(requestId=uuid4(), roleCode="planning"),
            )
        assert caught.value.code == code


async def test_old_request_does_not_reapply_after_cancellation(
    review_data: ApplicationData,
) -> None:
    data = review_data
    await make_public(data)
    body = ApplicationCreate(requestId=uuid4(), roleCode="planning")
    async with data.database.session() as session:
        response, _ = await service.submit_application(
            session, data.applicant_id, data.other_team_id, body
        )
    async with data.database.session() as session:
        await cancel_application(session, response.id, data.applicant_id, 1)
    async with data.database.session() as session:
        await session.execute(
            update(Profile)
            .where(Profile.profile_id == data.applicant_id)
            .values(is_public=False)
        )
        await session.commit()
    async with data.database.session() as session:
        replayed, created = await service.submit_application(
            session, data.applicant_id, data.other_team_id, body
        )
        assert (
            not created and replayed.status == "canceled" and replayed.id == response.id
        )


async def test_http_requires_auth_csrf_and_camel_case(
    review_data: ApplicationData,
) -> None:
    values = {"requestId": str(uuid4()), "roleCode": "planning"}
    path = f"/api/v1/teams/{review_data.other_team_id}/applications"
    async with creation_client(review_data, None) as client:
        assert (await client.post(path, json=values)).status_code == 401
    async with creation_client(review_data, review_data.applicant_id) as client:
        assert (
            await client.post(path, json=values, headers={"X-CSRF-Token": "bad"})
        ).status_code == 403
        assert (
            await client.post(path, json=values | {"role_code": "planning"})
        ).status_code == 422
        assert (
            await client.post(path, json=values | {"message": "\x00"})
        ).status_code == 422
